"""Ridge ablation: precision calibration, pair interactions and typed template roles.

No backpropagation. Source Run split unchanged. No post-Run state in features.
CPU supplies matched Cell inputs; Metal computes dense messages and ridge scores.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time
import numpy as np
import mlx.core as mx
from context_ridge import prepare, weights, encode_gpu, metrics, proposal_packets


def typed_roles(trace, width=32, normalize_effects=False):
    # Same operation/argument role has the same vector across different rules.
    # Rule IDs and labels are deliberately absent from the vector definition.
    keys={}
    for run in trace['runs']:
        for binding in run['audit']['bindings']:
            for port in binding['eq_ports']:
                keys.setdefault((binding['rule'],port['slot']),len(keys))
    def code(key):
        seed=int.from_bytes(hashlib.sha256(json.dumps(key,sort_keys=True).encode()).digest()[:8],'little')
        return np.random.default_rng(seed).normal(0,1/np.sqrt(width),width).astype(np.float32)
    vectors=[]
    for rid,slot in keys:
        rule=trace['recipe']['rules'][rid];tokens=[('sort',rule['slots'][slot]['sort'])]
        phases=[('query',rule['query'])]+([] if normalize_effects else [('effect',rule['effects'])])
        for phase,ops in phases:
            for op in ops:
                call=op.get('call',{});kind=op.get('kind','query')
                signature=(phase,kind,call)
                for i,arg in enumerate(op.get('args',[])):
                    if arg.get('slot')==slot:tokens.append((signature,'arg',i))
                if op.get('dst')==slot:tokens.append((signature,'dst'))
                if op.get('arg',{}).get('slot')==slot:tokens.append((signature,'copy-source'))
        if normalize_effects:
            # Copies are compiler aliases. Resolve them before describing roles,
            # so a union of copied inputs and a direct union share one feature.
            env={i:[(i,())] for i in range(len(rule['slots']))}
            def leaves(arg):return env.get(arg.get('slot'),[])
            for op in rule['effects']:
                kind=op['kind'];call=op.get('call',{})
                if kind=='copy':env[op['dst']]=list(leaves(op['arg']));continue
                if kind in ('construct','compute'):
                    env[op['dst']]=[(i,((kind,json.dumps(call,sort_keys=True),pos),)+path)
                        for pos,arg in enumerate(op['args']) for i,path in leaves(arg)]
                args=list(op.get('args',[]))
                if 'value' in op:args.append(op['value'])
                for pos,arg in enumerate(args):
                    for i,path in leaves(arg):
                        if i==slot:tokens.append(('effect',kind,call,'endpoint' if kind=='union' else pos,path))
        vectors.append(sum((code(t) for t in tokens),np.zeros(width,np.float32))/np.sqrt(len(tokens)))
    return np.array(vectors,np.float32)


def structured_encode(a, role, nroots, ncells, random_weights):
    scalar_w,self_w,context_w,random_w=random_weights
    msg=mx.tanh(role[a['roles']]+a['scalars'][a['owners']]@scalar_w)
    pooled=mx.zeros((nroots,32)).at[a['roots']].add(msg)
    counts=mx.zeros((nroots,)).at[a['roots']].add(mx.ones(a['roots'].shape))
    pooled=pooled/mx.sqrt(mx.maximum(1,counts[:,None]))
    local=mx.zeros((a['roots'].shape[0],32)).at[a['local_roots']].add(msg)
    lc=mx.zeros((a['roots'].shape[0],)).at[a['local_roots']].add(mx.ones(a['roots'].shape))
    local=local/mx.sqrt(mx.maximum(1,lc[:,None]))
    port=mx.tanh(msg@self_w+(local[a['local_roots']]+pooled[a['roots']])@context_w)
    cell=mx.zeros((ncells,64)).at[a['owners']].add(port)
    degree=mx.zeros((ncells,)).at[a['owners']].add(mx.ones(a['owners'].shape))
    cell=mx.tanh(cell/mx.sqrt(mx.maximum(1,degree[:,None])))
    a_port,b_port=port[a['left']],port[a['right']]
    x=mx.concatenate([cell[a['pair_owner']],a_port+b_port,mx.abs(a_port-b_port),a_port*b_port],axis=1)
    return mx.concatenate([mx.ones((x.shape[0],1)),x,mx.tanh(x@random_w)],axis=1)


def select(x,y,train,valid):
    # Fit standardization on training rows only; intercept is untouched.
    mean=x[train].mean(axis=0);scale=x[train].std(axis=0)
    mean[0]=0;scale[0]=1;scale=np.maximum(scale,.01)
    z=(x-mean)/scale
    best=None;tr=z[train].astype(np.float64);target=y[train]
    for positive_weight in (1.,4.,20.):
        weight=np.where(target>0,positive_weight,1.)
        gram=tr.T@(tr*weight[:,None]);rhs=tr.T@(target*weight)
        for regularizer in (.1,10.,1000.):
            penalty=np.eye(tr.shape[1])*regularizer;penalty[0,0]=0
            coef=np.linalg.solve(gram+penalty,rhs).astype(np.float32)
            scores=z[valid]@coef
            for threshold in np.linspace(.05,.95,37):
                m=metrics(scores,y[valid],threshold)
                # F0.5 weighs precision more heavily without rewarding silence.
                f05=1.25*m['tp']/max(1,1.25*m['tp']+.25*m['fn']+m['fp'])
                key=(f05,-m['fp'],m['tp'])
                if best is None or key>best[0]:
                    best=(key,coef,dict(positive_weight=positive_weight,regularizer=regularizer,threshold=float(threshold),validation_f05=f05))
    _,coef,config=best
    # Fold standardization into readout: runtime adds no normalization pass.
    folded=coef/scale;folded[0]-=np.dot(mean/scale,coef)
    return folded,config


def main():
    p=argparse.ArgumentParser();p.add_argument('trace',type=Path);p.add_argument('output',type=Path);p.add_argument('--proposals',type=Path);args=p.parse_args()
    trace=json.loads(args.trace.read_text());started=time.perf_counter();a,records,nroots,nroles=prepare(trace)
    roles=typed_roles(trace);normalized=typed_roles(trace,normalize_effects=True);prep=time.perf_counter()-started
    n=len(trace['steps']);train=(a['ordinals']<=int(n*.6))&~a['unsupported'];valid=(a['ordinals']>int(n*.6))&(a['ordinals']<=int(n*.8))&~a['unsupported'];test=(a['ordinals']>int(n*.8))&~a['unsupported']
    assert mx.metal.is_available();mx.set_default_device(mx.gpu)
    ga={k:mx.array(a[k]) for k in ('owners','roots','local_roots','roles','scalars','left','right','pair_owner')}
    old_w=[mx.array(w) for w in weights(nroles)]
    rng=np.random.default_rng(803);rw=[mx.array(rng.normal(0,1/np.sqrt(i),(i,j)).astype(np.float32)) for i,j in [(16,32),(32,64),(32,64),(256,256)]]
    groles=mx.array(roles);normalized_roles=mx.array(normalized)
    variants={};best=None
    for name,encode in [('calibration_only',lambda data:encode_gpu(data,old_w,nroots,len(records),True)),('typed_pair_interactions',lambda data:structured_encode(data,groles,nroots,len(records),rw)),('alias_normalized_roles',lambda data:structured_encode(data,normalized_roles,nroots,len(records),rw))]:
        started=time.perf_counter();features=mx.compile(encode)(ga);mx.eval(features);encoding=time.perf_counter()-started
        x=np.array(features);started=time.perf_counter();coef,config=select(x,a['labels'],train,valid);fitting=time.perf_counter()-started
        gcoef=mx.array(coef);fused=mx.compile(lambda data:encode(data)@gcoef)
        started=time.perf_counter();prediction=fused(ga);mx.eval(prediction);elapsed=time.perf_counter()-started;scores=np.array(prediction)
        np.testing.assert_allclose(scores,x@coef,rtol=1e-3,atol=3e-4)
        threshold=config['threshold']
        result=dict(**config,dimensions=x.shape[1],gpu_encode_first_seconds=encoding,ridge_search_seconds=fitting,gpu_fused_first_seconds=elapsed,**{split:metrics(scores[mask],a['labels'][mask],threshold) for split,mask in [('train',train),('validation',valid),('test',test),('all',np.ones(len(scores),bool))]})
        variants[name]=result
        if best is None or config['validation_f05']>best[0]:best=(config['validation_f05'],name,scores,threshold)
    if args.proposals:args.proposals.write_text(json.dumps(proposal_packets(trace,best[2],best[3])))
    positive_rules=set(a['rids'][train & (a['labels']>0)].tolist())
    unseen=int(sum(int(r) not in positive_rules for r in a['rids'][valid & (a['labels']>0)]))
    out=dict(validation_positive_pairs_without_training_positive_rule=unseen,scope='actual matched Cell inputs; Metal floating inference; replay only',backpropagation=False,cpu_prepare_seconds=prep,selection='validation F0.5 only; chronological 60/20/20 Run split',selected=best[1],variants=variants,program_sha256=trace['program_sha256'],trace_sha256=hashlib.sha256(args.trace.read_bytes()).hexdigest(),gpu_completed_bindings=0)
    args.output.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))

if __name__=='__main__':main()
