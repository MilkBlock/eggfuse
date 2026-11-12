"""Ridge kernel capacity/regularization study; frozen finite structural split."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('kernel_teacher', ROOT/'benchmarks/cell-real-state/study.py')
t = importlib.util.module_from_spec(spec); spec.loader.exec_module(t)


class Model:
    def __init__(self, centers, degree, bound):
        self.centers, self.degree, self.bound = centers, degree, bound

    def features(self, z):
        return np.concatenate([z, (1+z@self.centers.T/z.shape[1])**self.degree], 1)

    def fit(self, x, actions, y, reg):
        f = self.features(x).astype(np.float64)
        self.bank = []
        for a in range(17):
            take = actions == a
            xx, yy = f[take], (y-x)[take].astype(np.float64)
            mx, my = xx.mean(0), yy.mean(0)
            scale = np.maximum(xx.std(0), .05)
            xx = (xx-mx)/scale; yy = yy-my
            if len(xx) < xx.shape[1]:
                w = xx.T@np.linalg.solve(xx@xx.T+reg*np.eye(len(xx)), yy)
            else:
                w = np.linalg.solve(xx.T@xx+reg*np.eye(xx.shape[1]), xx.T@yy)
            w = w/scale[:, None]
            self.bank.append((w.astype(np.float32), (my-mx@w).astype(np.float32)))

    def step(self, z, actions):
        f = self.features(z)
        result = z.copy()
        for a, (w,b) in enumerate(self.bank):
            keep = actions == a
            result[keep] += f[keep]@w+b
        return np.clip(result, -self.bound, self.bound)

    def save(self, path, mean, basis, scale, decoder):
        np.savez(path, centers=self.centers, degree=self.degree, bound=self.bound,
                 w=np.stack([p[0] for p in self.bank]), bias=np.stack([p[1] for p in self.bank]),
                 mean=mean, basis=basis, scale=scale, decoder_w=decoder[0], decoder_b=decoder[1])


class Adapter:
    def __init__(self, path):
        self.p = dict(np.load(path)); p = self.p
        self.model = Model(p['centers'], int(p['degree']), p['bound'])
        self.model.bank = list(zip(p['w'], p['bias']))

    def encode(self, facts):
        p = self.p
        return ((facts-p['mean'])@p['basis'])/p['scale']

    def step(self, z, actions):
        return self.model.step(z, actions)

    def decode(self, z):
        return z@self.p['decoder_w']+self.p['decoder_b']


def load_adapter(path):
    return Adapter(path)


def score(model, z, facts, target, mask, decoder):
    source = np.repeat(np.flatnonzero(mask),17); actions = np.tile(np.arange(17),mask.sum())
    pred = model.step(z[source], actions)
    single = ((pred@decoder[0]+decoder[1]>=.5)==facts[target[source,actions]]).all(1).mean()
    ids = np.tile(np.flatnonzero(mask),4); current=z[ids].copy(); all_ok=np.ones(len(ids),bool)
    events=np.random.default_rng(17).integers(0,17,(12,len(ids)))
    events[2]=15; events[5]=16; events[8]=events[7]
    for a in events:
        current=model.step(current,a); ids=target[ids,a]
        all_ok &= np.isfinite(current).all(1)&((current@decoder[0]+decoder[1]>=.5)==facts[ids]).all(1)
    return dict(single=float(single), trace=float(all_ok.mean()))


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    _,facts,target,train,valid,test=t.dataset()
    mean=facts[train].mean(0);_,_,vt=np.linalg.svd(facts[train]-mean,full_matrices=False)
    src,act=np.where(train[:,None]&train[target]);dst=target[src,act]
    log=[];best=None
    # Fixed screen: retain all training covariance directions, reduce regularization.
    for d in (32,35):
        basis=vt[:d].T;scale=np.maximum(((facts[train]-mean)@basis).std(0),.1)
        z=((facts-mean)@basis)/scale
        decoder=t.ridge(z[train],facts[train],.001)
        bound=np.maximum(np.abs(z[train]).max(0)*1.25,1.)
        for degree in (2,3,4):
            for reg in (.001,.1,10.):
                model=Model(z[train],degree,bound);model.fit(z[src],act,z[dst],reg)
                val=score(model,z,facts,target,valid,decoder)
                row=dict(dimension=d,degree=degree,reg=reg,iteration=0,validation=val)
                log.append(row);print(json.dumps(row),flush=True)
                quality=(val['trace'],val['single'])
                if best is None or quality>best[0]:
                    best=(quality,row);model.save(args.output/'screen.npz',mean,basis,scale,decoder)
    adapter=load_adapter(args.output/'screen.npz');m=adapter.model;pp=adapter.p
    z=adapter.encode(facts);decoder=(pp['decoder_w'],pp['decoder_b'])
    selected=best[1];reg=selected['reg']
    m.save(args.output/'model.npz',pp['mean'],pp['basis'],pp['scale'],decoder)
    rng=np.random.default_rng(441);allowed=[np.flatnonzero(train[target[s]]) for s in range(len(z))]
    second=np.array([rng.choice(allowed[d]) for d in dst]);end=target[dst,second];ok=train[target[src,second]]
    for iteration in range(1,9):
        predicted=m.step(z[src],act);other=m.step(z[src[ok]],second[ok])
        x=np.concatenate([z[src],predicted,predicted,other]);a=np.concatenate([act,act,second,act[ok]])
        y=np.concatenate([z[dst],z[dst],z[end],z[end[ok]]]);m.fit(x,a,y,reg)
        val=score(m,z,facts,target,valid,decoder)
        row=dict(selected,iteration=iteration,validation=val);log.append(row);print(json.dumps(row),flush=True)
        quality=(val['trace'],val['single'])
        if quality>best[0]:
            best=(quality,row);m.save(args.output/'model.npz',pp['mean'],pp['basis'],pp['scale'],decoder)
    final=load_adapter(args.output/'model.npz')
    result=dict(scope='finite teacher, FP32 numerical ridge; no runtime takeover',selection=best[1],validation=log,
                test=score(final.model,final.encode(facts),facts,target,test,decoder),
                source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (args.output/'results.json').write_text(json.dumps(result,indent=2)+'\n');print('RESULT',result['selection'],result['test'])


if __name__=='__main__':main()
