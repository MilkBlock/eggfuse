"""Train independent query/key encoders on committed correlated RHS slots from training families only."""
import argparse
import json
from pathlib import Path
import numpy as np
import torch
from torch import nn
from plan import compile_program

F=16;BITS=10
def features(keys):
    x=keys.astype(np.uint64,copy=True)
    with np.errstate(over='ignore'):
        x^=x>>np.uint64(30);x*=np.uint64(0xbf58476d1ce4e5b9)
        x^=x>>np.uint64(27);x*=np.uint64(0x94d049bb133111eb)
        x^=x>>np.uint64(31)
    return torch.tensor((((x[:,None]>>np.arange(F,dtype=np.uint64))&1).astype(np.float32)*2-1))

def train(a):
    torch.set_num_threads(1);torch.manual_seed(a.seed);rng=np.random.default_rng(a.seed)
    collection=json.loads((a.corpus/'collection.json').read_bytes());values=[];counts={}
    for n,c in collection.items():
        if c['split']!='train':continue
        image=a.corpus/n/'input';plans=compile_program(image);rules=json.loads((image/'ingress.json').read_bytes())['rules']
        local=[]
        with np.load(a.corpus/n/'device/output.npz') as z:
            for r in z['rhs']:
                rid=int(r[1]);p=plans[rid]
                if not p:continue
                rule=rules[rid];inputs=dict(zip(rule['inputs'],map(int,r[4:])))
                for atom,pick,cols in p['ins']:
                    if pick:
                        for col in cols:
                            slot=rule['q'][atom][1][col]
                            if slot in inputs:local.append(inputs[slot])
        counts[n]=len(local);values.append(np.array(local,np.int64))
    assert len(values)==4 and all(len(v)>0 for v in values)
    q,k=nn.Linear(F,BITS,bias=False),nn.Linear(F,BITS,bias=False)
    opt=torch.optim.Adam([*q.parameters(),*k.parameters()],lr=.012)
    for step in range(700):
        data=values[step%4]
        raw=data[rng.integers(len(data),size=192)].view(np.uint64)^rng.integers(2**63,dtype=np.uint64)
        x=features(raw);zq=q(x);zk=k(x)
        u=zq.tanh();v=zk.tanh();similarity=u@v.T
        positive=torch.tensor(raw[:,None]==raw)
        contrast=(similarity.logsumexp(1)-similarity.masked_fill(~positive,-1e9).logsumexp(1)).mean()
        loss=contrast+2*((u-v)**2).mean()+.04*((u.abs()-1)**2+(v.abs()-1)**2).mean()
        opt.zero_grad();loss.backward();opt.step()
    test=features(rng.integers(2**63,size=8192,dtype=np.uint64))
    with torch.inference_mode():
        diff=((q(test)>0)!=(k(test)>0)).sum(1)
    a.out.mkdir(parents=True,exist_ok=False)
    w=dict(q=q.weight.detach().tolist(),k=k.weight.detach().tolist(),seed=a.seed,train=counts,
           features=F,bits=BITS,updates=700,held_symbol_hamming_histogram=torch.bincount(diff,minlength=BITS+1).tolist())
    (a.out/'model.json').write_text(json.dumps(w,separators=(',',':'))+'\n')
    print(counts,w['held_symbol_hamming_histogram'],flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('corpus',type=Path);p.add_argument('out',type=Path);p.add_argument('--seed',type=int,default=1703);train(p.parse_args())
