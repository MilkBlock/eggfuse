"""GPU Cell recurrence with learned persistent boundary channels.

One row is a whole Cell. Per-boundary channels are part of its state, not
independently scheduled node tasks. Bake supplies fixed request projections.
Only original boundary ports are represented in this experiment; newly created
ports need a future layout extension and are explicitly excluded from rollout.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import mlx.core as mx
from whole_cell_ridge import D, code, encode, request, train
from dominator_completion import freeze, compose
from cell_token_successors import compile_catalog, match_consumer

B=16


def symbols(facts):
    return sorted({freeze(v) for _,args,*_ in facts for v in args},key=repr)


def boundary(facts,ports,mapping=None):
    """Teacher/bootstrap only; never called on the device's intermediate state."""
    facts=sorted({(n,tuple(freeze(v) for v in args)) for n,args,*_ in facts},key=repr)
    roles={v:np.zeros(B,np.float32) for v in symbols(facts)}
    for n,args in facts:
        for pos,v in enumerate(args):roles[v]+=code(('boundary-role',n,pos))[:B]
    # Include adjacent roles so two F inputs with different local contexts differ.
    result={v:roles[v].copy() for v in roles}
    for n,args in facts:
        for pos,v in enumerate(args):
            for other,w in enumerate(args):
                result[v]+=np.tanh(roles[w])*code(('boundary-edge',n,pos,other))[:B]
    aliases=dict((freeze(a),freeze(b)) for a,b in mapping) if mapping is not None else {v:v for v in ports}
    return np.array([np.tanh(result[aliases[v]]+(code(aliases[v])[:B] if aliases[v][0]=='literal' else 0)) for v in ports],np.float32).reshape(-1,B)


def state(facts,ports,capacity,mapping=None):
    channels=np.zeros((capacity,B),np.float32)
    channels[:len(ports)]=boundary(facts,ports,mapping)
    return np.concatenate([encode(facts),channels.reshape(-1)])


def projection(binding,ports,capacity):
    index={p:i for i,p in enumerate(ports)}
    p=np.zeros((capacity,B,D),np.float32)
    for slot,symbol in binding:
        symbol=freeze(symbol)
        if symbol not in index:raise ValueError('request needs unrepresented boundary')
        # Fixed dense mixing associated with query input slot, not opaque port ID.
        for j in range(B):p[index[symbol],j]+=code(('boundary-request',slot,j))
    return p.reshape(capacity*B,D)/np.sqrt(max(1,len(binding)))



def fit_boundary_basis(states,targets,training,rank):
    if rank<1 or rank>states.shape[1]-D:raise ValueError('invalid boundary rank')
    # Uncentered SVD: zero/padded channels remain zero without a runtime bias.
    examples=np.concatenate([states[training,D:],targets[training,D:]],axis=0)
    _,_,vt=np.linalg.svd(examples,full_matrices=False)
    if rank>len(vt):raise ValueError('rank exceeds training sample dimension')
    return vt[:rank].T.astype(np.float32)


def compress_state(states,basis):
    return np.concatenate([states[:,:D],states[:,D:]@basis],axis=1)


def compress_projection(projections,basis):
    # Bake folds the basis into fixed wiring; the GPU never reconstructs ports.
    return np.matmul(basis.T,projections)


def audit_boundary(states,basis):
    return states[:,D:] if basis is None else states[:,D:]@basis.T


def features(states,queries,projections,w,xp):
    h=states[:,:D]
    attached=xp.tanh(xp.matmul(states[:,None,D:],projections)[:,0,:])
    q=xp.tanh(queries+attached)
    x=xp.concatenate([h,q,h*q,xp.abs(h-q),attached],axis=1)
    return xp.concatenate([xp.ones((len(states),1),dtype=xp.float32),x,xp.tanh(x@w)],axis=1)


def step(states,queries,projections,w,coef,xp):
    out=features(states,queries,projections,w,xp)@coef
    emit=out[:,-1]>=.5
    return xp.where(emit[:,None],states+out[:,:-1],states),emit


def main():
    parser=argparse.ArgumentParser();parser.add_argument('program',type=Path);parser.add_argument('targets',type=Path);parser.add_argument('output',type=Path);parser.add_argument('--predictions',type=Path);parser.add_argument('--boundary-rank',type=int);args=parser.parse_args()
    program=json.loads(args.program.read_text());data=json.loads(args.targets.read_text())
    if program['sha256']!=data['program_sha256']:raise ValueError('program mismatch')
    recipe=program['recipe'];rules=recipe['rules'];tables={t['name']:t for t in recipe['tables']};catalog=compile_catalog(recipe)
    capacity=max(len(symbols(r['source'])) for r in data['targets'])
    states=[];queries=[];projections=[];targets=[];novel=[];roots=[];chains=[];unrepresented=0;port_counts=[]
    for row in data['targets']:
        source=row['source'];ports=symbols(source);port_counts.extend([len(ports)]*2);completion=row['completion'];binding=catalog['edges'][row['edge']]['inputs'];rule=rules[row['consumer']]
        s=state(source,ports,capacity);t=state(completion['facts'],ports,capacity,completion['source_map']);q=request(rule,binding);p=projection(binding,ports,capacity)
        states.extend([s,s]);targets.extend([t,s]);queries.extend([q,np.zeros(D,np.float32)]);projections.extend([p,np.zeros_like(p)]);novel.extend([completion['novel'],False]);roots.extend([row['producer']]*2)
        if row['producer']%5==0 and completion['novel'] and len(chains)<64:
            facts=[(n,tuple(freeze(v) for v in vs),True) for n,vs in completion['facts']]
            # Exact inverse maps are compile-time wiring, not inferred IDs.
            quotient={freeze(a):freeze(b) for a,b in completion['source_map']};inverse={}
            for port in ports:inverse.setdefault(quotient[port],port)
            found=False
            for consumer in rules:
                bindings,exhausted=match_consumer(consumer,facts,limit=32)
                if exhausted:continue
                for match in bindings:
                    second,reason=compose(facts,consumer,match['inputs'],tables)
                    if reason or not second['novel']:continue
                    if any(freeze(v) not in inverse for _,v in match['inputs']):unrepresented+=1;continue
                    next_binding=[(slot,inverse[freeze(v)]) for slot,v in match['inputs']]
                    q2=request(consumer,match['inputs']);p2=projection(next_binding,ports,capacity)
                    second_map={freeze(a):freeze(b) for a,b in second['source_map']}
                    composed=[(port,second_map[quotient[port]]) for port in ports]
                    gold2=state(second['facts'],ports,capacity,composed)
                    chains.append((s,q,p,q2,p2,gold2,row['producer'],len(ports)));found=True;break
                if found:break
    s=np.array(states,np.float32);q=np.array(queries,np.float32);p=np.array(projections,np.float32);t=np.array(targets,np.float32);n=np.array(novel,bool);roots=np.array(roots)
    full_target=t.copy();basis=None
    if args.boundary_rank is not None:
        basis=fit_boundary_basis(s,t,roots%5>=2,args.boundary_rank)
        s=compress_state(s,basis);t=compress_state(t,basis);p=compress_projection(p,basis)
    rng=np.random.default_rng(119);w=rng.normal(0,1/16,(5*D,256)).astype(np.float32)
    x=features(s,q,p,w,np);coef,fit=train(x,np.column_stack([t-s,n.astype(np.float32)]),roots%5>=2,roots%5==1)
    if not mx.metal.is_available():raise RuntimeError('Metal required')
    mx.set_default_device(mx.gpu);gw=mx.array(w);gc=mx.array(coef)
    def gpu_step(a,b,c):return step(a,b,c,gw,gc,mx)
    pred,emit=mx.compile(gpu_step)(mx.array(s),mx.array(q),mx.array(p));mx.eval(pred,emit)
    pred=np.array(pred);emit=np.array(emit);reference,e=step(s,q,p,w,coef,np)
    np.testing.assert_allclose(pred,reference,rtol=2e-3,atol=5e-4);np.testing.assert_array_equal(emit,e)
    live=np.repeat(np.arange(capacity)[None,:]<np.array(port_counts)[:,None],B,axis=1)
    decoded_boundary=audit_boundary(pred,basis)
    metrics={}
    for name,mask in [('train',roots%5>=2),('validation',roots%5==1),('test',roots%5==0)]:
        metrics[name]=dict(cases=int(mask.sum()),novel=int(n[mask].sum()),emitted=int(emit[mask].sum()),false_emissions=int((mask&emit&~n).sum()),missed_emissions=int((mask&~emit&n).sum()),body_rmse=float(np.sqrt(np.mean((pred[mask,:D]-t[mask,:D])**2))),live_boundary_rmse=float(np.sqrt(np.mean(((decoded_boundary[mask]-full_target[mask,D:])**2)[live[mask]]))),unchanged_body_rmse=float(np.sqrt(np.mean((s[mask,:D]-t[mask,:D])**2))))
    compression_reconstruction={}
    if basis is not None:
        reconstructed=full_target[:,D:]@basis@basis.T
        for name,mask in [('train',roots%5>=2),('validation',roots%5==1),('test',roots%5==0)]:
            compression_reconstruction[name]=float(np.sqrt(np.mean(((reconstructed[mask]-full_target[mask,D:])**2)[live[mask]])))
    result=dict(compression_target_live_reconstruction_rmse=compression_reconstruction,scope='standalone learned whole-Cell and original-boundary Metal recurrence; no runtime takeover',program_sha256=program['sha256'],targets_sha256=hashlib.sha256(args.targets.read_bytes()).hexdigest(),backpropagation=False,boundary_rank=args.boundary_rank,basis_training='training producer source and target states only; uncentered SVD',capacity=capacity,boundary_width=B,state_float_count=s.shape[1],request_projection_floats_per_row=int(np.prod(p.shape[1:])),fit=fit,metrics=metrics,limitations=['Same finite producer-family split, not unseen workload','Only original boundary ports; new-port requests excluded explicitly','Request projections supplied by Bake; GPU match discovery not implemented','No exact semantic decoder or ownership retirement authorization','Dense per-request projections are expensive prototype storage, not a performance claim'])
    if chains:
        a,b,c,d,e,gold,origins,counts=zip(*chains);a,b,c,d,e,gold=[np.array(v,np.float32) for v in (a,b,c,d,e,gold)]
        if basis is not None:
            a=compress_state(a,basis);c=compress_projection(c,basis);e=compress_projection(e,basis)
        def rollout(a,b,c,d,e):
            first,live1=gpu_step(a,b,c);last,live2=gpu_step(first,d,e);live2=live1&live2
            return mx.where(live2[:,None],last,first),live1,live2
        last,e1,e2=mx.compile(rollout)(*[mx.array(v) for v in (a,b,c,d,e)]);mx.eval(last,e1,e2)
        first,l1=step(a,b,c,w,coef,np);second,l2=step(first,d,e,w,coef,np);reference=np.where((l1&l2)[:,None],second,first)
        np.testing.assert_allclose(np.array(last),reference,rtol=2e-3,atol=8e-4)
        result['rollout']=dict(chains=len(chains),initial_producers=len(set(origins)),excluded_new_boundary_requests=unrepresented,first_emissions=int(np.array(e1).sum()),second_emissions=int(np.array(e2).sum()),body_rmse=float(np.sqrt(np.mean((np.array(last)[:,:D]-gold[:,:D])**2))),live_boundary_rmse=float(np.sqrt(np.mean(((audit_boundary(np.array(last),basis)-gold[:,D:])**2)[np.repeat(np.arange(capacity)[None,:]<np.array(counts)[:,None],B,axis=1)]))),intermediate_cpu_reads=0,teacher_state_supplied_between_steps=False)
    if args.predictions:
        args.predictions.write_text(json.dumps(dict(program_sha256=program['sha256'],targets_sha256=result['targets_sha256'],predictions=pred[:,:D].tolist(),emitted=emit.tolist(),producer_roots=roots.tolist(),order='each target followed by its identity control'))+'\n')
    args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
