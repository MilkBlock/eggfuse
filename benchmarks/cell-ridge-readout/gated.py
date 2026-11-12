"""Robust observation ridge; frozen latent dynamics, no observation feedback."""
import sys
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'benchmarks/cell-ridge-attractor'))
spec=importlib.util.spec_from_file_location('frozen_attractor',ROOT/'benchmarks/cell-ridge-attractor/staged_gated.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)


def features(z,centers,kind):
    if kind.startswith('poly'):
        hidden=(1+z@centers.T/17)**int(kind[4:])
    else:
        dist=np.maximum((z*z).sum(1)[:,None]+(centers*centers).sum(1)-2*z@centers.T,0)
        hidden=np.exp(-dist/float(kind[3:]))
    return np.concatenate([z,hidden],1)


def ridge(x,y,reg):
    x,y=x.astype(np.float64),y.astype(np.float64)
    mx,my=x.mean(0),y.mean(0);scale=np.maximum(x.std(0),.05)
    xx=(x-mx)/scale
    w=np.linalg.solve(xx.T@xx+reg*np.eye(x.shape[1]),xx.T@(y-my))/scale[:,None]
    return w.astype(np.float32),(my-mx@w).astype(np.float32)


class Adapter:
    def __init__(self,path):
        self.p=dict(np.load(path));self.original=base.load_adapter(Path(str(self.p['base_path'])))

    def encode(self,f):return self.original.encode(f)
    def step(self,z,a):return self.original.step(z,a)
    def decode(self,z):
        p=self.p
        return features(z,p['centers'],str(p['kind']))@p['w']+p['b']


def load_adapter(path):return Adapter(path)


def trajectory_inputs(model,z,facts,target,mask):
    ids=np.tile(np.flatnonzero(mask),4);current=z[ids].copy();preds=[];labels=[]
    events=np.random.default_rng(17).integers(0,17,(12,len(ids)))
    events[2]=15;events[5]=16;events[8]=events[7]
    for a in events:
        current=model.step(current,a);ids=target[ids,a]
        preds.append(current.copy());labels.append(facts[ids])
    return np.concatenate(preds),np.concatenate(labels),len(ids)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    base_path=ROOT/'out/cell-ridge-attractor/staged-gated/model.npz';model=base.load_adapter(base_path)
    _,facts,target,train,valid,test=base.kernel.t.dataset();z=model.encode(facts)
    src,act=np.where(train[:,None]&train[target]);dst=target[src,act]
    predicted=model.step(z[src],act)
    rng=np.random.default_rng(117);allowed=[np.flatnonzero(train[target[i]]) for i in range(len(z))]
    second=np.array([rng.choice(allowed[i]) for i in dst]);end=target[dst,second]
    second_pred=model.step(predicted,second)
    vx,vy,vn=trajectory_inputs(model,z,facts,target,valid)
    best=None;logs=[]
    for noise in (0.,.05):
        clean=np.repeat(z[train],8,axis=0)
        x=np.concatenate([z[train],predicted,second_pred,clean+rng.normal(0,noise,clean.shape)])
        y=np.concatenate([facts[train],facts[dst],facts[end],np.repeat(facts[train],8,axis=0)])
        for kind in ('poly2','poly4','rbf4','rbf16','rbf32'):
            xx=features(x,z[train],kind);vv=features(vx,z[train],kind)
            for reg in (.01,1.):
                w,b=ridge(xx,y,reg);out=vv@w+b
                exact=((out>=.5)==vy).all(1)
                quality=(exact.reshape(12,vn).all(0).mean(),exact.mean())
                row=dict(noise=noise,kind=kind,reg=reg,validation_trace=float(quality[0]),validation_step=float(quality[1]))
                logs.append(row);print(row,flush=True)
                if best is None or quality>best[0]:
                    best=(quality,row)
                    np.savez(args.output/'model.npz',base_path=str(base_path),centers=z[train],kind=kind,w=w,b=b)
    final=Adapter(args.output/'model.npz')
    tx,ty,tn=trajectory_inputs(model,z,facts,target,test);out=final.decode(tx)
    exact=((out>=.5)==ty).all(1)
    ids=np.repeat(np.flatnonzero(test),17);actions=np.tile(np.arange(17),test.sum())
    single=((final.decode(final.step(z[ids],actions))>=.5)==facts[target[ids,actions]]).all(1)
    result=dict(selection=best[1],validation=logs,test_trace=float(exact.reshape(12,tn).all(0).mean()),
                test_single=float(single.mean()),test_initial=float(((final.decode(z[test])>=.5)==facts[test]).all(1).mean()),
                source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                scope='readout-only learned correction, never fed back to latent execution')
    (args.output/'results.json').write_text(json.dumps(result,indent=2)+'\n');print('RESULT',result['selection'],result['test_single'],result['test_trace'])


if __name__=='__main__':main()
