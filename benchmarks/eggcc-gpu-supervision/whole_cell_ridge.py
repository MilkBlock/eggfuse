"""Learn complete dominator-Cell codes rather than isolated Eq or RHS columns.

Offline Bake supplies bounded semantic targets and request interfaces. GPU
predicts a new whole-Cell code and whether to emit it, then feeds its own output
into another completion. No backpropagation or intermediate CPU encoding.
This is NOT yet a full runtime, exact state decoder or transfer authorization.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import mlx.core as mx
from dominator_completion import compose,freeze
from cell_token_successors import match_consumer,compile_catalog

D=64

def code(key):
    seed=int.from_bytes(hashlib.sha256(json.dumps(key,sort_keys=True).encode()).digest()[:8],'little')
    return np.random.default_rng(seed).normal(0,1/np.sqrt(D),D).astype(np.float32)


def encode(facts):
    facts=sorted(set((n,tuple(freeze(a) for a in args)) for n,args,*_ in facts),key=repr)
    roles={}
    for name,args in facts:
        for pos,symbol in enumerate(args):
            roles.setdefault(symbol,np.zeros(D,np.float32))[:] += code(('role',name,pos))
    ports={s:np.tanh(v+(code(s) if s[0]=='literal' else 0)) for s,v in roles.items()}
    total=np.zeros(D,np.float32)
    for name,args in sorted(set(facts),key=repr):
        value=code(('constructor',name))
        for pos,s in enumerate(args):value=value+ports[s]*code(('position',pos))*np.sqrt(D)
        total+=np.tanh(value)
    return total/np.sqrt(max(1,len(set(facts))))


def request(rule,binding):
    # Template metadata only. It does not include the target closure or novelty.
    terms=[]
    for op in rule['effects']:
        if op['kind']!='copy':terms.append((op['kind'],op.get('call',{}),len(op.get('args',[]))))
    # Preserve boundary sharing without exposing incidental local port numbers.
    groups={};pattern=[]
    for slot,symbol in binding:
        symbol=freeze(symbol);pattern.append((slot,groups.setdefault(symbol,len(groups))))
    return np.tanh(sum((code(('request',t)) for t in terms),np.zeros(D,np.float32))+code(('binding',pattern)))


def feature(h,q,w,xp):
    x=xp.concatenate([h,q,h*q,xp.abs(h-q)],axis=1)
    return xp.concatenate([xp.ones((x.shape[0],1),dtype=xp.float32),x,xp.tanh(x@w)],axis=1)


def train(x,y,train_mask,val_mask):
    mean=x[train_mask].mean(0);mean[0]=0
    scale=np.maximum(x[train_mask].std(0),.02);scale[0]=1
    z=(x-mean)/scale;a=z[train_mask].astype(np.float64);b=y[train_mask].astype(np.float64)
    gram=a.T@a;rhs=a.T@b;best=None
    for alpha in (.1,1.,10.,100.):
        penalty=np.eye(a.shape[1])*alpha;penalty[0,0]=0
        coef=np.linalg.solve(gram+penalty,rhs).astype(np.float32)
        mse=float(np.mean((z[val_mask]@coef-y[val_mask])**2))
        if best is None or mse<best[0]:best=(mse,alpha,coef)
    mse,alpha,coef=best;coef=coef/scale[:,None];coef[0]-=(mean[:,None]*coef).sum(0)
    return coef,dict(alpha=alpha,validation_target_mse=mse)


def metrics(pred,target,novel,emit):
    return dict(cases=len(target),true_completions=int(novel.sum()),emitted=int(emit.sum()),
        false_emissions=int((emit&~novel).sum()),missed_completions=int((~emit&novel).sum()),
        latent_rmse=float(np.sqrt(np.mean((pred-target)**2))))


def main():
    p=argparse.ArgumentParser();p.add_argument('program',type=Path);p.add_argument('targets',type=Path);p.add_argument('output',type=Path);args=p.parse_args()
    program=json.loads(args.program.read_text());data=json.loads(args.targets.read_text())
    if data['program_sha256']!=program['sha256']:raise ValueError('program mismatch')
    rules=program['recipe']['rules'];tables={t['name']:t for t in program['recipe']['tables']}
    hs=[];qs=[];ys=[];novels=[];roots=[];chains=[];chain_origins=[];catalog=compile_catalog(program['recipe'])
    # Original producer families stay together; identity requests are explicit
    # negative controls, not duplicated positive targets.
    for row in data['targets']:
        h=encode(row['source']);rule=rules[row['consumer']]
        # Reconstruct the matching interface from Bake metadata, not labels.
        edge=catalog['edges'][row['edge']];q=request(rule,edge['inputs'])
        target=encode(row['completion']['facts']);n=row['completion']['novel']
        hs.extend([h,h]);qs.extend([q,np.zeros(D,np.float32)]);ys.extend([target,h]);novels.extend([n,False]);roots.extend([row['producer']]*2)
        # One deterministic second request per root family, bounded before fitting.
        if row['producer']%5==0 and len(chains)<64 and n:
            facts=[(name,tuple(freeze(v) for v in values),True) for name,values in row['completion']['facts']]
            for cid,consumer in enumerate(rules):
                bindings,full=match_consumer(consumer,facts,limit=32)
                if full:continue
                found=False
                for binding in bindings:
                    second,reason=compose(facts,consumer,binding['inputs'],tables)
                    if reason or not second['novel']:continue
                    chains.append((h,q,request(consumer,binding['inputs']),target,encode(second['facts'])));chain_origins.append((row['producer'],row['consumer'],cid));found=True;break
                if found:break
    h=np.array(hs,np.float32);q=np.array(qs,np.float32);target=np.array(ys,np.float32);novel=np.array(novels,bool);roots=np.array(roots)
    tr=roots%5>=2;va=roots%5==1;te=roots%5==0
    rng=np.random.default_rng(119);w=rng.normal(0,1/16,(4*D,256)).astype(np.float32)
    x=feature(h,q,w,np);y=np.column_stack([target-h,novel.astype(np.float32)])
    coef,fit=train(x,y,tr,va)
    assert mx.metal.is_available();mx.set_default_device(mx.gpu);gw=mx.array(w);gc=mx.array(coef)
    def step(state,query):
        out=feature(state,query,gw,mx)@gc;emit=out[:,-1]>=.5
        return mx.where(emit[:,None],state+out[:,:D],state),emit
    pred,emit=mx.compile(step)(mx.array(h),mx.array(q));mx.eval(pred,emit)
    pred=np.array(pred);emit=np.array(emit)
    raw=x@coef;reference=np.where((raw[:,-1]>=.5)[:,None],h+raw[:,:D],h)
    np.testing.assert_allclose(pred,reference,rtol=1e-3,atol=3e-4)
    result=dict(program_sha256=program['sha256'],targets_sha256=hashlib.sha256(args.targets.read_bytes()).hexdigest(),scope='offline whole-Cell semantic completion targets; Metal learned-code proposal only',backpropagation=False,fit=fit,split='producer modulo 5: 2-4 train, 1 validation, 0 test; not a fresh workload holdout',
        metrics={name:metrics(pred[m],target[m],novel[m],emit[m]) for name,m in [('train',tr),('validation',va),('test',te)]},
        no_change_baseline_rmse=float(np.sqrt(np.mean((h[te]-target[te])**2))),
        limitations=['Lossy whole-Cell codes have no exact semantic decoder yet','Candidate requests come from Bake, not GPU discovery of all matches','No source Run legality, ownership retirement or global saturation established','Successful emission is a proposal, not authorized ownership transfer'])
    if chains:
        a,b,c,gold1,gold2=[np.array(v,np.float32) for v in zip(*chains)]
        def rollout(state,q1,q2):
            first,live1=step(state,q1);second,live2=step(first,q2)
            live2=live1&live2
            return first,mx.where(live2[:,None],second,first),live1,live2
        first,last,e1,e2=mx.compile(rollout)(mx.array(a),mx.array(b),mx.array(c));mx.eval(first,last,e1,e2)
        r1=feature(a,b,w,np)@coef;l1=r1[:,-1]>=.5
        s1=np.where(l1[:,None],a+r1[:,:D],a)
        r2=feature(s1,c,w,np)@coef;l2=l1&(r2[:,-1]>=.5)
        s2=np.where(l2[:,None],s1+r2[:,:D],s1)
        np.testing.assert_allclose(np.array(last),s2,rtol=1e-3,atol=5e-4)
        result['generated_state_consumption']=dict(chains=len(chains),distinct_initial_producers=len({r[0] for r in chain_origins}),selection='first 64 admissible two-step cases from test producer families',first_emissions=int(np.array(e1).sum()),second_emissions=int(np.array(e2).sum()),final_latent_rmse=float(np.sqrt(np.mean((np.array(last)-gold2)**2))),no_change_baseline_rmse=float(np.sqrt(np.mean((a-gold2)**2))),intermediate_cpu_reads=0,teacher_state_supplied_between_steps=False)
    args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
