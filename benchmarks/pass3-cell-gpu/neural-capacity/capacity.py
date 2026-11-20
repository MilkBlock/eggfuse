"""Matched family and capacity sweep for a whole-pass two-level neural proof generator."""
import argparse
import json
from pathlib import Path
import sys
from time import perf_counter_ns

import numpy as np
import torch
from torch import nn

FOREST=Path(__file__).resolve().parents[1]/'whole-pass-generation'
sys.path.insert(0,str(FOREST))
from policy import Policy,packet,labels,read


def model(tables,rules,target):
    net=Policy(tables,rules)
    fixed=sum(p.numel() for module in (net.root,net.table,net.consumer) for p in module.parameters())
    width=min(range(8,1025),key=lambda w:abs(fixed + w*w+43*w+1-target))
    net.child=nn.Sequential(nn.Linear(40,width),nn.Tanh(),nn.Linear(width,width),nn.Tanh(),nn.Linear(width,1))
    return net


def train(a):
    torch.set_num_threads(1)
    names=[n for n,v in read(a.corpus/'collection.json').items() if v['split']=='train']
    assert len(names)==4
    inputs={}
    for n in names:
        p=packet(a.corpus/n/'input',a.corpus/n/'program.json')
        inputs[n]=(torch.tensor(p['root_x'],device='mps'),torch.tensor(p['child_x'],device='mps'),
                   torch.tensor(p['candidates'],device='mps'),labels(p,a.captures/n).to('mps'))
    tables=p['table_count'];rules=max(1024,p['rules'])
    for seed in (1703,1709):
        for target in (40000,160000,640000):
            for families in (2,4):
                torch.manual_seed(seed);rng=np.random.default_rng(seed)
                net=model(tables,rules,target).to('mps');opt=torch.optim.Adam(net.parameters(),lr=.002)
                chosen=names[:families];sampled=0
                torch.mps.synchronize();start=perf_counter_ns()
                for step in range(a.updates):
                    x,y,c,truth=inputs[chosen[step%families]]
                    idx=torch.tensor(rng.integers(len(c),size=128),dtype=torch.long,device='mps')
                    _,score=net(x,y[idx],c[idx])
                    loss=nn.functional.binary_cross_entropy_with_logits(score,truth[idx],pos_weight=torch.tensor(2.,device='mps'))
                    opt.zero_grad();loss.backward();opt.step();sampled+=len(idx)
                torch.mps.synchronize();ms=(perf_counter_ns()-start)/1e6
                net=net.cpu().eval();stats={}
                with torch.inference_mode():
                    for n,(x,y,c,truth) in inputs.items():
                        _,score=net(x.cpu(),y.cpu(),c.cpu())
                        keep=score>=0;correct=truth.cpu().bool()
                        stats[n]=dict(positive=int(correct.sum()),raw=int(keep.sum()),correct=int((keep & correct).sum()),
                                      used_for_training=n in chosen)
                path=a.out/f'{seed}-{target}-{families}';path.mkdir(parents=True,exist_ok=False)
                state=dict(state=net.state_dict(),tables=tables,rules=rules,target=target)
                torch.save(state,path/'weights.pt')
                record=dict(seed=seed,target=target,train=chosen,parameters=sum(p.numel() for p in net.parameters()),
                            bytes=sum(p.numel()*p.element_size() for p in net.parameters()),train_ms=ms,
                            updates=a.updates,source_graph_draws=a.updates,candidate_draws=sampled,train_counts=stats)
                (path/'record.json').write_text(json.dumps(record)+'\n');print(path, round(ms),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('corpus','captures','out'):p.add_argument(k,type=Path)
    p.add_argument('--updates',type=int,default=400)
    train(p.parse_args())
