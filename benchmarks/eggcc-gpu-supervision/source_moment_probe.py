"""Dynamic source second moments: observed-wiring feature experiment, not runtime."""
import argparse, hashlib, json, time
from pathlib import Path
import numpy as np
import mlx.core as mx
from multi_entry_ridge import dataset, arrays, pooling, features, projection, metric
from whole_cell_ridge import train
from collect_observed_corpus import read_bytes


def moment(messages, valid, xp):
    # Messages already contain template role coefficients, but not pooling's
    # outer sqrt(edge count). Padding must not affect the denominator.
    safe=xp.where(valid[...,None],messages,0)
    return xp.sum(safe*safe,axis=-2)/xp.maximum(xp.sum(valid,axis=-1),1)[...,None]


def moments(nodes, states):
    out=np.zeros((len(nodes),128),np.float32)
    for j,n in enumerate(nodes):
        if n['edges']:
            messages=np.array([states[i]*w for i,w in n['edges']],np.float32)
            out[j]=moment(messages,np.ones(len(messages),bool),np)
    return out


def load(path):
    manifest=json.loads(path.read_text());nodes=[]
    for entry in manifest['cases']:
        if entry['status']!='complete':continue
        if entry['split']!=manifest['partition']:raise ValueError('partition mismatch')
        raw=read_bytes(Path(entry['trace']))
        if hashlib.sha256(raw).hexdigest()!=entry['trace_sha256']:raise ValueError('trace hash')
        group=dataset(json.loads(raw),4,False,'class-history-neighborhood-input')
        offset=len(nodes)
        for n in group:n['edges']=[(i+offset,w) for i,w in n['edges']]
        nodes.extend(group)
    return nodes,manifest


def matrix(nodes, states, w, extra):
    s,q,_=arrays(nodes);pool=pooling(nodes,states);base=features(s,q,pool,w,np)
    if extra=='moments':return np.concatenate([base,moments(nodes,states)],axis=1)
    if extra=='seed_source_quadratics':
        local=pool[:,:128]
        return np.concatenate([base,s*s*local,s*local*local],axis=1)
    return base


def rollout(nodes,w,coef,extra):
    _,_,target=arrays(nodes);state=np.where(np.array([n['valid'] for n in nodes])[:,None],0,target)
    for depth in range(max(n['depth'] for n in nodes)+1):
        ids=[i for i,n in enumerate(nodes) if n['valid'] and n['depth']==depth]
        if not ids:continue
        batch=[nodes[i] for i in ids]
        state[ids]=np.tanh(matrix(batch,state,w,extra)@coef)
    return state


def main():
    p=argparse.ArgumentParser()
    for k in ('training','validation','output'):p.add_argument(k,type=Path)
    a=p.parse_args();started=time.monotonic()
    tr,tm=load(a.training);va,vm=load(a.validation)
    if tm['partition']!='train' or vm['partition']!='validation' or tm['manifest_sha256']!=vm['manifest_sha256']:raise ValueError('split provenance')
    offset=len(tr)
    for n in va:n['edges']=[(i+offset,w) for i,w in n['edges']]
    nodes=tr+va;_,_,target=arrays(nodes);valid=np.array([n['valid'] for n in nodes]);trainmask=valid&(np.arange(len(nodes))<offset);valmask=valid&~trainmask
    w=projection(1408);reports={}
    for extra in ('baseline','moments','seed_source_quadratics'):
        x=matrix(nodes,target,w,extra);coef,fit=train(x,np.arctanh(np.clip(target,-.999,.999)),trainmask,valmask)
        direct=np.tanh(x@coef);recurrent=rollout(nodes,w,coef,extra)
        gpu=mx.tanh(mx.array(x)@mx.array(coef));mx.eval(gpu)
        reports[extra]=dict(fit=fit,feature_columns=x.shape[1],coefficient_bytes=coef.nbytes,
            validation_direct=metric(direct,target,valmask),validation_rollout=metric(recurrent,target,valmask),
            validation_multiple_direct=metric(direct,target,valmask&np.array([n['multiple'] for n in nodes])),
            gpu_direct_max_abs=float(np.max(abs(np.array(gpu)-direct))))
    result=dict(scope='train/validation observed-wiring ablation; not autonomous GPU runtime or semantic accuracy',backpropagation=False,
        corpus_sha256=tm['manifest_sha256'],training_manifest_sha256=hashlib.sha256(a.training.read_bytes()).hexdigest(),
        validation_manifest_sha256=hashlib.sha256(a.validation.read_bytes()).hexdigest(),reports=reports,
        seconds=time.monotonic()-started,extra_dynamic_floats_per_cell=dict(moments=128,seed_source_quadratics=256),
        limitations=['Observed provider wiring; historical visibility not proved','Token RMSE is not exact Eq accuracy','CPU prepares features; GPU readout checked separately','No held-out test consulted; no runtime model replaced'])
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
