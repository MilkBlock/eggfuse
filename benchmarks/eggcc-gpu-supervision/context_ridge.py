"""Whole-program shared-port floating messages and no-backprop Eq readout.

Replay of actual pre-Run Cell matches. Exact CPU routing is charged, GPU sums
dense messages and performs ridge inference. No predicted union is committed.
"""
import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import time

import mlx.core as mx
import numpy as np


def prepare(trace, rename=lambda x:x):
    root_index={};role_index={};local_index={};owners=[];roots=[];local_roots=[];roles=[];scalars=[]
    left=[];right=[];pair_owner=[];labels=[];ordinals=[];rids=[];unsupported=[]
    rng=np.random.default_rng(701)
    # Fixed per-slot scalar projection, independent of labels and global IDs.
    max_slots=max(len(r['slots']) for r in trace['recipe']['rules'])
    scalar_weights=rng.normal(0,.3,(max_slots,5,16)).astype(np.float32)
    records=[]
    for run in trace['runs']:
        for index,binding in enumerate(run['audit']['bindings']):
            owner=len(records);ports=binding['eq_ports'];offset=len(owners)
            scalar=np.zeros(16,np.float32);bad=False
            for value in binding['values']:
                if 'eq' in value['value']:continue
                v=value['value'].get('value')
                if isinstance(v,(int,bool)) and -(1<<63)<=v<(1<<63):
                    bits=int(v)&((1<<64)-1)
                    # Exact 16-bit limbs enter f32 without rounding away i64
                    # identity. They are features, not a replacement i64 ALU.
                    feature=[math.copysign(math.log1p(abs(v))/64,v)]+[(bits>>(16*j)&65535)/65536 for j in range(4)]
                elif isinstance(v,str):
                    digest=hashlib.sha256((value['value']['sort']+':'+v).encode()).digest()
                    feature=[int.from_bytes(digest[j*2:j*2+2],'little')/32768-1 for j in range(5)]
                elif isinstance(v,float) and math.isfinite(v):
                    feature=[math.copysign(math.log1p(abs(v))/64,v),math.tanh(v/32),0,0,0]
                else:
                    bad=True;continue
                scalar+=np.tanh(np.array(feature,np.float32)@scalar_weights[value['slot']])
            for port in ports:
                root_key=(run['ordinal'],port['sort'],rename(port['before']))
                role_key=(binding['rule'],port['slot'])
                roots.append(root_index.setdefault(root_key,len(root_index)))
                local_roots.append(local_index.setdefault((owner,port['sort'],rename(port['before'])),len(local_index)))
                roles.append(role_index.setdefault(role_key,len(role_index)))
                owners.append(owner)
            for i,a in enumerate(ports):
                for j,b in enumerate(ports[:i]):
                    if a['sort']==b['sort'] and a['before']!=b['before']:
                        left.append(offset+j);right.append(offset+i);pair_owner.append(owner)
                        # Labels are used only by fitting and evaluation, never routing.
                        labels.append(int(a['after']==b['after']))
                        ordinals.append(run['ordinal']);rids.append(binding['rule']);unsupported.append(bad)
            scalars.append(scalar)
            records.append(dict(run=run['ordinal'],binding=index,rule=binding['rule'],unsupported_scalar=bad))
    arrays={k:np.array(v,np.int32) for k,v in dict(owners=owners,roots=roots,local_roots=local_roots,roles=roles,
        left=left,right=right,pair_owner=pair_owner,ordinals=ordinals,rids=rids).items()}
    arrays.update(scalars=np.array(scalars,np.float32),labels=np.array(labels,np.float32),
                  unsupported=np.array(unsupported,bool))
    return arrays,records,len(root_index),len(role_index)


def weights(nroles):
    rng=np.random.default_rng(702)
    shapes=[(nroles,16),(16,16),(16,32),(16,32),(96,192)]
    return [rng.normal(0,1/np.sqrt(s[0] if i else 16),s).astype(np.float32)
            for i,s in enumerate(shapes)]


def encode_numpy(a,w,nroots,ncells,context):
    role,scalar,self_w,context_w,random_w=w
    msg=np.tanh(role[a['roles']]+a['scalars'][a['owners']]@scalar)
    pooled=np.zeros((nroots,16),np.float32)
    if context:np.add.at(pooled,a['roots'],msg)
    local=np.zeros((len(a['roots']),16),np.float32);np.add.at(local,a['local_roots'],msg)
    port=np.tanh(msg@self_w+(local[a['local_roots']]+pooled[a['roots']])@context_w)
    cell=np.zeros((ncells,32),np.float32);np.add.at(cell,a['owners'],port)
    degree=np.maximum(1,np.bincount(a['owners'],minlength=ncells)).astype(np.float32)
    cell=np.tanh(cell/np.sqrt(degree[:,None]))
    x=np.concatenate([cell[a['pair_owner']],port[a['left']],port[a['right']]],axis=1)
    return np.concatenate([np.ones((len(x),1),np.float32),x,np.tanh(x@random_w)],axis=1)


def encode_gpu(a,w,nroots,ncells,context):
    role,scalar,self_w,context_w,random_w=w
    msg=mx.tanh(role[a['roles']]+a['scalars'][a['owners']]@scalar)
    pooled=mx.zeros((nroots,16),mx.float32)
    if context:pooled=pooled.at[a['roots']].add(msg)
    local=mx.zeros((a['roots'].shape[0],16),mx.float32).at[a['local_roots']].add(msg)
    port=mx.tanh(msg@self_w+(local[a['local_roots']]+pooled[a['roots']])@context_w)
    cell=mx.zeros((ncells,32),mx.float32).at[a['owners']].add(port)
    degree=mx.zeros((ncells,),mx.float32).at[a['owners']].add(mx.ones(a['owners'].shape))
    cell=mx.tanh(cell/mx.sqrt(mx.maximum(1,degree[:,None])))
    x=mx.concatenate([cell[a['pair_owner']],port[a['left']],port[a['right']]],axis=1)
    return mx.concatenate([mx.ones((x.shape[0],1)),x,mx.tanh(x@random_w)],axis=1)


def metrics(scores,y,threshold):
    pred=scores>=threshold;truth=y.astype(bool)
    tp=int((pred&truth).sum());fp=int((pred&~truth).sum());fn=int((~pred&truth).sum())
    return dict(pairs=len(y),positive_pairs=int(truth.sum()),tp=tp,fp=fp,fn=fn,
        precision=tp/(tp+fp) if tp+fp else None,recall=tp/(tp+fn) if tp+fn else None,
        f2=5*tp/(5*tp+4*fn+fp) if 5*tp+4*fn+fp else 0.)


def fit(x,y,regularizer):
    # Fixed positive-class weight; only training labels affect the fit.
    weight=np.where(y>0,20.,1.)
    xd=x.astype(np.float64);gram=xd.T@(xd*weight[:,None])
    penalty=np.eye(x.shape[1])*regularizer;penalty[0,0]=0
    return np.linalg.solve(gram+penalty,xd.T@(y*weight)).astype(np.float32)


def proposal_packets(trace, scores, threshold):
    """Replay packets for native audit, including empty source Runs.

    The order mirrors prepare(), but only pre-Run metadata defines claims.
    execution=0 is an explicit saved replay tag, not live freshness evidence.
    """
    packets={s['ordinal']:dict(execution=0,program=trace['program_sha256'],
        run=s['ordinal'],epoch=s['epoch'],equalities=[]) for s in trace['steps']}
    cursor=0
    for run in trace['runs']:
        for index,binding in enumerate(run['audit']['bindings']):
            ports=binding['eq_ports']
            for i,a in enumerate(ports):
                for b in ports[:i]:
                    if a['sort']==b['sort'] and a['before']!=b['before']:
                        if scores[cursor]>=threshold:
                            packets[run['ordinal']]['equalities'].append(dict(binding=index,
                                rule=binding['rule'],left=min(a['slot'],b['slot']),right=max(a['slot'],b['slot'])))
                        cursor+=1
    if cursor!=len(scores):raise ValueError('prediction count does not match candidate pairs')
    return list(packets.values())


def main():
    p=argparse.ArgumentParser();p.add_argument('trace',type=Path);p.add_argument('output',type=Path);p.add_argument('--proposals',type=Path);args=p.parse_args()
    trace=json.loads(args.trace.read_text());assert trace.get('relations')
    started=time.perf_counter();a,records,nroots,nroles=prepare(trace);prepare_seconds=time.perf_counter()-started
    renamed,_,_,_=prepare(trace,lambda x:2**100+37*x)
    for key in a:np.testing.assert_array_equal(a[key],renamed[key])
    del renamed
    nrun=len(trace['steps']);train=a['ordinals']<=int(nrun*.6)
    valid=(a['ordinals']>int(nrun*.6))&(a['ordinals']<=int(nrun*.8));test=a['ordinals']>int(nrun*.8)
    pair_sets=np.array([trace['steps'][int(i)-1]['ruleset'] for i in a['ordinals']])
    admitted=~a['unsupported'];train &= admitted;valid &= admitted;test &= admitted
    w=weights(nroles);assert mx.metal.is_available();mx.set_default_device(mx.gpu)
    started=time.perf_counter();ga={k:mx.array(a[k]) for k in ('owners','roots','local_roots','roles','scalars','left','right','pair_owner')}
    gw=[mx.array(v) for v in w];mx.eval(ga,gw);upload_seconds=time.perf_counter()-started
    variants={}
    for context in (False,True):
        started=time.perf_counter();cpu=encode_numpy(a,w,nroots,len(records),context);cpu_encode=time.perf_counter()-started
        kernel=mx.compile(lambda data:encode_gpu(data,gw,nroots,len(records),context))
        started=time.perf_counter();features=kernel(ga);mx.eval(features);gpu_encode=time.perf_counter()-started
        np.testing.assert_allclose(np.array(features),cpu,rtol=1e-3,atol=2e-5)
        best=None;started=time.perf_counter()
        for regularizer in (.01,1.,100.):
            coef=fit(cpu[train],a['labels'][train],regularizer)
            scores=cpu[valid]@coef
            for threshold in (.1,.2,.3,.4,.5,.6,.7,.8,.9):
                m=metrics(scores,a['labels'][valid],threshold)
                candidate=(m['f2'],-m['fp'])
                if best is None or candidate>best[0]:best=(candidate,coef,regularizer,threshold,m)
        fit_seconds=time.perf_counter()-started
        _,coef,regularizer,threshold,validation=best
        # Keep the encoded state on device: the ridge readout directly consumes it.
        gcoef=mx.array(coef);readout=mx.compile(lambda f:f@gcoef)
        started=time.perf_counter();prediction=readout(features);mx.eval(prediction);readout_seconds=time.perf_counter()-started
        scores=np.array(prediction)
        fused=mx.compile(lambda data:encode_gpu(data,gw,nroots,len(records),context)@gcoef)
        started=time.perf_counter();joint=fused(ga);mx.eval(joint);joint_seconds=time.perf_counter()-started
        joint_scores=np.array(joint)
        np.testing.assert_allclose(joint_scores,scores,rtol=1e-3,atol=2e-4)
        classification_disagreements=int(((joint_scores>=threshold)!=(scores>=threshold)).sum())
        scores=joint_scores
        if context and args.proposals:
            args.proposals.write_text(json.dumps(proposal_packets(trace,scores,threshold)))
        np.testing.assert_allclose(scores,cpu@coef,rtol=1e-3,atol=2e-4)
        observed=set(hashlib.sha256(row.tobytes()).digest() for row in cpu[train])
        overlap=sum(hashlib.sha256(row.tobytes()).digest() in observed for row in cpu[test])
        variants['context' if context else 'local']=dict(
            regularizer=regularizer,threshold=threshold,validation=validation,
            test=metrics(scores[test],a['labels'][test],threshold),
            train=metrics(scores[train],a['labels'][train],threshold),
            test_exact_feature_rows_seen_in_train=overlap,cpu_encode_seconds=cpu_encode,
            gpu_encode_first_request_seconds=gpu_encode,ridge_fit_seconds=fit_seconds,
            gpu_readout_first_request_seconds=readout_seconds,
            fused_device_first_request_seconds=joint_seconds,
            fused_classification_disagreements=classification_disagreements,
            per_ruleset_test={name:metrics(scores[test & (pair_sets==name)],
                                a['labels'][test & (pair_sets==name)],threshold)
                              for name in sorted(set(pair_sets[test]))})
    out=dict(scope='Whole-program pre-Run port message encoding and ridge prediction of input-port Eq deltas; replay only',
        trace_sha256=hashlib.sha256(args.trace.read_bytes()).hexdigest(),program_sha256=trace['program_sha256'],
        cells=len(records),ports=len(a['roots']),root_groups=nroots,role_codes=nroles,
        candidate_pairs=len(a['labels']),positive_pairs=int(a['labels'].sum()),
        cpu_prepare_seconds=prepare_seconds,upload_seconds=upload_seconds,
        routing_bytes=sum(a[k].nbytes for k in ('owners','roots','local_roots','roles','left','right','pair_owner')),
        split=dict(kind='chronological source Run',train_end=int(nrun*.6),validation_end=int(nrun*.8),test_end=nrun),
        scalar_encoding='i64 sign-log plus four exact 16-bit limbs; String fixed hash features; exact typed values retained by CPU',
        unsupported_scalar_pairs=int(a['unsupported'].sum()),renaming_invariance=True,backpropagation=False,
        variants=variants,gpu_completed_bindings=0,
        limitations=['Only observed input-port Eq changes; no new-node or query completion',
        'CPU supplies matched instances, exact pre-Run root routing and scalar encoding',
        'Within-Run messages never cross into another Run; post-Run roots are labels only',
        'Chronological test has few positive changes; no generalization claim from high total accuracy',
        'String feature hashing and dense pooling are lossy, not equality proofs',
        'Fixed weights and all role layouts are compiler metadata; only ridge uses training targets',
        'Feature arrays read back for offline fitting/validation only; no predicted union committed',
        'Cold timings include compilation and cannot establish end-to-end speedup'])
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps(out,indent=2))


if __name__=='__main__':main()
