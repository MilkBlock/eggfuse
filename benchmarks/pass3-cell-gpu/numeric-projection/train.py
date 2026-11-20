"""Fit separate structural and numeric heads to four training families of actual source traces."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np
import torch
from torch import nn

from adapter import specialize
from plan import plan,read
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'recurrent-generator'))
from capture import inputs,verify


def train(a):
    a.out.mkdir(parents=True,exist_ok=a.reuse_capture)
    data={};plans_by_id={}
    for name,case in read(a.corpus/'collection.json').items():
        if case['split']!='train':continue
        image,program,gold=inputs(a.corpus,a.ref,name)
        rules=plan(program,image)
        plans_by_id.update({p['rule']:p for p in rules})
        fn=specialize(rules,read(image/'ingress.json'),direct=False)
        dest=a.out/name
        if not a.reuse_capture:fn(image/'device.json',a.reader,a.ref/'ports-1703.pt',2048,2,dest)
        verify(dest,gold,image)
        with np.load(dest/'numeric.npz') as n:
            data[name]=(n['features'].copy(),n['args'].copy(),n['outcomes'].copy())
    assert len(data)==4
    torch.set_num_threads(1)
    f=np.concatenate([d[0] for d in data.values()])
    feat=torch.tensor(f[:,4:11],dtype=torch.float32)/32
    labels=torch.tensor(f[:,13]>0,dtype=torch.float32)
    rules=sorted({int(o[1]) for _,_,out in data.values() for o in out if o[0]})
    for seed in (1703,1709):
        torch.manual_seed(seed)
        model=nn.Linear(7,1);opt=torch.optim.Adam(model.parameters(),lr=.03)
        for step in range(400):
            logits=model(feat)[:,0]
            loss=nn.functional.binary_cross_entropy_with_logits(logits,labels,pos_weight=torch.tensor(3.))
            opt.zero_grad();loss.backward();opt.step()
        with torch.no_grad():scores=model(feat)[:,0].numpy()
        thresholds={}
        for rid in rules:
            seen=(f[:,1]==rid)&(f[:,13]>0)
            if seen.any():thresholds[rid]=float(np.quantile(scores[seen],.10))
        numeric={}
        # All structural leaf operands come from witnessed input facts, before any arithmetic result.
        # Learn function-specific coefficients with ridge; the exact target is supervision only.
        for rid in rules:
            X=[];y=[]
            for _,values,out in data.values():
                for o in out[(out[:,1]==rid)&(out[:,7]>0)]:
                    idx=int(o[7]-1);X.append([*values[idx,:4],1]);y.append(o[4])
            if not X:continue
            X=np.asarray(X,dtype=np.float64);y=np.asarray(y,dtype=np.float64)
            coeff=np.linalg.solve(X.T@X+.25*np.eye(5),X.T@y)
            numeric[rid]=coeff.astype(np.float32).tolist()
        shapes={}
        for rid,p in plans_by_id.items():
            if rid in numeric:shapes.setdefault(f"{len(p['slots'])}/{p['literal']}",[]).append(numeric[rid])
        by_shape={k:np.mean(v,axis=0).tolist() for k,v in shapes.items()}
        artifact=dict(thresholds=thresholds,shape_numeric=by_shape,seed=seed,training_families=sorted(data),observations=len(labels),route_winners=int(labels.sum()),
                      selector=model.weight.detach()[0].tolist()+[model.bias.item()],numeric=numeric)
        (a.out/f'model-{seed}.json').write_text(json.dumps(artifact,indent=1)+'\n')
        print(seed,artifact['observations'],artifact['route_winners'],list(numeric),flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for k in ('corpus','ref','reader','out'):ap.add_argument(k,type=Path)
    ap.add_argument('--reuse-capture',action='store_true')
    train(ap.parse_args())
