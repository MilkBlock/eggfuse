"""Equal-budget PyTorch corpus ablation. All learned weights run as a tiny native Rust MLP."""
import argparse
from collections import Counter,defaultdict
from copy import deepcopy
import gzip
import json
from pathlib import Path
import numpy as np
import torch
from torch import nn
from harness import read

BUDGET=2400
def reserved(family):
    return int(family[:8],16)%5==0

def load(capture,name):
    with gzip.open(capture/name/'events.json.gz','rt') as f:return json.load(f)

def bake(training):
    counts=Counter();support=defaultdict(set)
    for name,rows in training.items():
        unions=defaultdict(list)
        for r in rows:unions[r['union']].append(r)
        for members in unions.values():
            donors=[r for r in members if r['x'][2]]
            for d in donors:
                for r in members:
                    if (d['cell'],d['op'])==(r['cell'],r['op']):continue
                    for col in r['positions']:
                        edge=(d['table_name'],r['table_name'],col)
                        counts[edge]+=1;support[edge].add(name)
    candidates=[e for e in counts if len(support[e])>=2]
    selected=sorted(candidates,key=lambda e:(-counts[e],e))[:8]
    return dict(pool=len(candidates),selected=[list(e) for e in selected],tables=sorted({t for e in selected for t in e[:2]}))

def synthetic(rng):
    arity=int(rng.integers(1,7));cols=int(rng.integers(arity))
    keys=rng.integers(3,size=cols);result=int(rng.integers(3))
    if not (result==0 or (keys==0).any()):
        if cols and rng.random()<.5:keys[int(rng.integers(cols))]=0
        else:result=0
    dirty=bool(rng.random()<.13);bucket=2 if rng.random()<.12 else 1
    own=int(rng.integers(1,6));outs=int(rng.choice([0,0,0,1,1,2,3,4,8,14]))
    first_other=bool(outs and rng.random()<outs/(outs+own))
    x=[arity/8,cols/8,float(result==0),float(cols>0 and keys[0]==0),float(cols>0 and keys[0]==1),float(dirty),
       bucket/3,min(16,own+outs)/16,float(first_other),float(rng.random()<.5),rng.integers(0,17)/16,rng.integers(0,9)/8]
    return dict(x=x,fast=not dirty and bucket==1 and result==0 and not (keys==0).any(),external=bool(outs))

def edit(row,kind):
    e=deepcopy(row);x=e['x']
    if kind=='reader':
        if e['outside_count']>1:return None
        if e['outside_count']==1:
            e['outside_count']=0;e['uses']-=1;x[8]=0.
        else:
            e['outside_count']=1;e['uses']+=1 # A later independent owner leaves the first member unchanged.
        e['external']=bool(e['outside_count']);x[7]=min(e['uses'],16)/16
    elif kind=='collision':
        if e['hash_bucket']!=1:return None
        e['hash_bucket']=2;x[6]=2/3
    elif kind=='prior':
        if e['dirty']:return None
        e['dirty']=True;x[5]=1.
    else:raise ValueError(kind)
    e['fast']=bool(x[2]) and not e['key_from'] and not e['dirty'] and e['hash_bucket']==1
    return e

def dataset(training,style,rng):
    names=sorted(training);examples=[];counts=Counter()
    for n in names:
        quota=BUDGET//len(names);rows=training[n]
        if style=='synthetic':examples.extend(synthetic(rng) for _ in range(quota));continue
        npairs=quota//4 if style=='paired' else 0
        for j in range(npairs):
            kind=('reader','collision','prior')[j%3]
            while True:
                base=rows[int(rng.integers(len(rows)))];counter=edit(base,kind)
                if counter is not None:break
            examples.extend([base,counter]);counts[kind]+=1
        examples.extend(rows[int(i)] for i in rng.integers(len(rows),size=quota-2*npairs))
    assert len(examples)==BUDGET
    return examples,dict(counts)

class Head(nn.Module):
    def __init__(self):
        super().__init__();self.first=nn.Linear(12,12);self.last=nn.Linear(12,2)
    def forward(self,x):return self.last(self.first(x).relu())

def train(examples,seed):
    rng=np.random.default_rng(seed);torch.manual_seed(seed)
    x=torch.tensor(np.array([e['x'] for e in examples]),dtype=torch.float32)
    y=torch.tensor([[e['fast'],e['external']] for e in examples],dtype=torch.float32)
    head=Head();opt=torch.optim.Adam(head.parameters(),lr=.009)
    for _ in range(400):
        ix=rng.integers(len(examples),size=64)
        loss=nn.functional.binary_cross_entropy_with_logits(head(x[ix]),y[ix])
        opt.zero_grad();loss.backward();opt.step()
    return dict(first=head.first.weight.detach().tolist(),bias=head.first.bias.detach().tolist(),
                last=head.last.weight.detach().tolist(),offset=head.last.bias.detach().tolist())

def fit(capture,out):
    out.mkdir(parents=True,exist_ok=False);torch.set_num_threads(1)
    summary=read(capture/'capture.json')
    training={n:[r for r in load(capture,n) if not reserved(r['family'])] for n,s in summary.items() if s['split']=='train'}
    assert len(training)==4 and all(training.values())
    library=bake(training)
    for rs in training.values():
        for r in rs:r['x'][9]=float(r['table_name'] in library['tables'])
    risk=[r['weight']*r['uses'] for rs in training.values() for r in rs]
    report=dict(training=list(training),available={k:len(v) for k,v in training.items()},bake=library,
                risk90=int(np.percentile(risk,90)),examples=BUDGET,updates=400,batch=64,styles={})
    for seed in (1703,1709):
        for style in ('synthetic','real','paired'):
            examples,counts=dataset(training,style,np.random.default_rng(seed))
            key=f'{style}-{seed}';w=train(examples,seed)
            (out/f'{key}.json').write_text(json.dumps(w,separators=(',',':'))+'\n')
            report['styles'][key]=dict(examples=len(examples),pairs=counts,
                                     positive=sum(int(e['fast']) for e in examples),outside=sum(int(e['external']) for e in examples))
    (out/'manifest.json').write_text(json.dumps(report,indent=1)+'\n')
    print(report,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('capture',type=Path);p.add_argument('out',type=Path)
    a=p.parse_args();fit(a.capture,a.out)
