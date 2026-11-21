"""Train a batch demand forecast. Each label is an actual fresh root allocated later in source order."""
import argparse,cProfile,json,math
from pathlib import Path
from collections import Counter
import torch
from torch import nn
from driver import base,source

DONORS=('sum-bits','dot-product','jacobi-1d')

def capture(a):
    out={}
    for name in DONORS:
        prog,plans,req=source.common.config(a,name)
        with source.base.session(a.exp/'compact-vanilla-20261121/vanilla',prog) as get:gold=get({})
        rows={}
        with source.base.session(a.native,prog,plans) as get:
            for timing in ('run','page'):
                v=get(dict(base(req),spec_cells=dict(timing=timing,storage='capacity',policy='capture',cap=a.cap,audit=True)))
                assert v['state_sha']==gold['state_sha'] and v['multi']['total_rhs']==gold['rhs_count'] and v['runs']==gold['runs']
                samples=v['spec_cells']['samples'];assert samples and all(len(e)==7 for e in samples)
                hist=Counter()
                for epoch,rid,template,x,offers,wins,fresh in samples:
                    assert len(x)==8 and abs(x[0]-1)<1e-8 and 0<=fresh and 0<=wins<=offers
                    if timing=='run':assert x[7]==0
                    hist[(tuple(x),offers,wins,fresh)]+=1
                rows[timing]=dict(total=len(samples),offers=sum(e[4] for e in samples),wins=sum(e[5] for e in samples),
                    fresh=sum(e[6] for e in samples),events=[[list(x),o,w,f,n] for (x,o,w,f),n in sorted(hist.items())])
                print(name,timing,len(samples),rows[timing]['fresh'],flush=True)
        out[name]=rows
        (a.out/'donors.json').write_text(json.dumps(out,separators=(',',':'))+'\n')
    return out

def fit(data,cap):
    result={}
    for timing in ('run','page'):
        rows=[z for v in data.values() for z in v[timing]['events']]
        x=torch.tensor([z[0] for z in rows],dtype=torch.float64)
        y=torch.tensor([z[3] for z in rows],dtype=torch.float64);n=torch.tensor([z[4] for z in rows],dtype=torch.float64)
        assert (n*y).sum()>0 and (x[:,0]==1).all()
        gram=x.T@(n[:,None]*x)+torch.eye(x.shape[1],dtype=x.dtype)*.1
        initial=torch.linalg.solve(gram,x.T@(n*torch.log1p(y)))
        models={}
        for name,quantile in [('log-mean',None),('balanced',.5),('coverage',.8)]:
            w=nn.Parameter(initial.clone())
            if quantile is not None:
                opt=torch.optim.Adam([w],lr=.003)
                for _ in range(200):
                    pred=torch.expm1(torch.clamp(x@w, -.5, math.log1p(cap)))
                    err=y-pred
                    loss=(n*torch.maximum(quantile*err,(quantile-1)*err)).sum()/(n*y).sum()+.0005*(w-initial).square().mean()
                    opt.zero_grad();loss.backward();opt.step()
            with torch.no_grad():
                predicted=(torch.expm1(torch.clamp(x@w,0,math.log1p(cap)))+.5).floor()
                # Before the shared Run budget or serial-specific physical admission.
                models[name]=dict(weights=w.tolist(),requested=int((predicted*n).sum()),truth=int((y*n).sum()),
                                  overlap=int((torch.minimum(y,predicted)*n).sum()))
        result[timing]=models
    return dict(donors=list(data),cap=cap,models=result)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--cap',type=int,default=8192);a=p.parse_args();a.seed=1703
    a.out.mkdir(parents=True,exist_ok=False);torch.set_num_threads(1);data=capture(a)
    (a.out/'policy.json').write_text(json.dumps(fit(data,a.cap),indent=1)+'\n')
