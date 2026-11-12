"""Dense minimal boundary state; derived observations are readout-only."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from study import Model, t


def fit_readout(x,y,reg):
    x,y=x.astype(np.float64),y.astype(np.float64)
    mx,my=x.mean(0),y.mean(0);scale=np.maximum(x.std(0),.05)
    xx=(x-mx)/scale; yy=y-my
    w=xx.T@np.linalg.solve(xx@xx.T+reg*np.eye(len(xx)),yy)
    w/=scale[:,None]
    return w.astype(np.float32),(my-mx@w).astype(np.float32)


class Adapter:
    def __init__(self,path=None,**p):
        self.p=dict(np.load(path)) if path else p
        p=self.p
        self.model=Model(p['centers'],int(p['degree']),p['bound'])
        if 'w' in p:self.model.bank=list(zip(p['w'],p['bias']))

    def encode(self,facts):
        p=self.p
        return ((facts[:,p['columns']]-p['mean'])@p['basis'])/p['scale']

    def step(self,z,a):return self.model.step(z,a)

    def decode(self,z):
        p=self.p
        features=np.concatenate([z,(1+z@p['centers'].T/z.shape[1])**int(p['readout_degree'])],1)
        return features@p['decoder_w']+p['decoder_b']

    def save(self,path):
        p=dict(self.p,w=np.stack([w for w,b in self.model.bank]),bias=np.stack([b for w,b in self.model.bank]))
        np.savez(path,**p)


def load_adapter(path):return Adapter(path)


def score(adapter,z,facts,target,mask):
    ids=np.repeat(np.flatnonzero(mask),17);actions=np.tile(np.arange(17),mask.sum())
    out=adapter.decode(adapter.step(z[ids],actions))
    single=((out>=.5)==facts[target[ids,actions]]).all(1).mean()
    ids=np.tile(np.flatnonzero(mask),4);current=z[ids].copy();ok=np.ones(len(ids),bool)
    events=np.random.default_rng(17).integers(0,17,(12,len(ids)))
    events[2]=15;events[5]=16;events[8]=events[7]
    for a in events:
        current=adapter.step(current,a);ids=target[ids,a];out=adapter.decode(current)
        ok &= np.isfinite(out).all(1)&((out>=.5)==facts[ids]).all(1)
    return dict(single=float(single),trace=float(ok.mean()))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    _,facts,target,train,valid,test=t.dataset()
    columns=np.array([t.PAIRS.index(pair) for pair in t.BASE_PAIRS]+[153,154])
    raw=facts[:,columns];mean=raw[train].mean(0)
    _,_,vt=np.linalg.svd(raw[train]-mean,full_matrices=False);basis=vt.T
    scale=np.maximum(((raw[train]-mean)@basis).std(0),.1);z=((raw-mean)@basis)/scale
    centers=z[train];bound=np.maximum(np.abs(z[train]).max(0)*1.25,1.)
    readout_log=[];best_decoder=None
    for degree in (2,3,4):
        features=np.concatenate([z,(1+z@centers.T/17)**degree],1)
        for reg in (.001,1.):
            decoder=fit_readout(features[train],facts[train],reg)
            out=features[valid]@decoder[0]+decoder[1]
            quality=(((out>=.5)==facts[valid]).all(1).mean(),-np.mean((out-facts[valid])**2))
            row=dict(degree=degree,reg=reg,validation_initial=float(quality[0]));readout_log.append(row);print(row,flush=True)
            if best_decoder is None or quality>best_decoder[0]:best_decoder=(quality,row,decoder)
    base=dict(columns=columns,mean=mean,basis=basis,scale=scale,centers=centers,bound=bound,
              readout_degree=best_decoder[1]['degree'],decoder_w=best_decoder[2][0],decoder_b=best_decoder[2][1])
    src,act=np.where(train[:,None]&train[target]);dst=target[src,act]
    log=[];best=None
    for degree in (2,3,4,5):
        for reg in (.001,.1,10.):
            adapter=Adapter(**base,degree=degree);adapter.model.fit(z[src],act,z[dst],reg)
            val=score(adapter,z,facts,target,valid)
            row=dict(degree=degree,reg=reg,iteration=0,validation=val);log.append(row);print(row,flush=True)
            quality=(val['trace'],val['single'])
            if best is None or quality>best[0]:best=(quality,row);adapter.save(args.output/'screen.npz')
    adapter=Adapter(args.output/'screen.npz');adapter.save(args.output/'model.npz')
    selected=best[1];rng=np.random.default_rng(441)
    allowed=[np.flatnonzero(train[target[s]]) for s in range(len(z))]
    second=np.array([rng.choice(allowed[d]) for d in dst]);end=target[dst,second];ok=train[target[src,second]]
    for iteration in range(1,9):
        predicted=adapter.step(z[src],act);other=adapter.step(z[src[ok]],second[ok])
        x=np.concatenate([z[src],predicted,predicted,other]);a=np.concatenate([act,act,second,act[ok]])
        y=np.concatenate([z[dst],z[dst],z[end],z[end[ok]]]);adapter.model.fit(x,a,y,selected['reg'])
        val=score(adapter,z,facts,target,valid);row=dict(selected,iteration=iteration,validation=val)
        log.append(row);print(row,flush=True);quality=(val['trace'],val['single'])
        if quality>best[0]:best=(quality,row);adapter.save(args.output/'model.npz')
    final=Adapter(args.output/'model.npz')
    result=dict(scope='finite teacher; 17 real coordinates; nonlinear readout never feeds execution',
                selection=best[1],readout_selection=best_decoder[1],readout_validation=readout_log,validation=log,
                test=score(final,z,facts,target,test),
                test_initial=float(((final.decode(z[test])>=.5)==facts[test]).all(1).mean()),
                source_sha256={n:hashlib.sha256((Path(__file__).parent/n).read_bytes()).hexdigest() for n in ('compact.py','study.py')})
    (args.output/'results.json').write_text(json.dumps(result,indent=2)+'\n');print('RESULT',result['selection'],result['test'],result['test_initial'])


if __name__=='__main__':main()
