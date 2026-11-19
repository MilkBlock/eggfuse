"""Shared two-row proposal scores; train balance and locality on synthetic correlated joins."""
import argparse
import hashlib
import json
from pathlib import Path

import torch
from torch import nn


class RowRouter(nn.Module):
    def __init__(self):
        super().__init__()
        self.net=nn.Sequential(nn.Linear(8,12),nn.Tanh(),nn.Linear(12,2))

    def forward(self,code):
        bits=(code[...,None]>>torch.arange(8,device=code.device)) & 1
        return self.net(bits.float()*2-1)


def train(out,seed):
    if out.exists():raise FileExistsError(out)
    dev=torch.device('mps');torch.manual_seed(seed);g=torch.Generator().manual_seed(seed)
    m=RowRouter().to(dev);opt=torch.optim.Adam(m.parameters(),lr=.006)
    def rand(high,shape):return torch.randint(high,shape,generator=g).to(dev)
    for step in range(512):
        # Independent small join workloads. Repeated source keys have correlated
        # matches but independent local table/width features. No Pass 3 trace is used.
        keys=rand(64,(32,16));keys=keys.gather(1,rand(16,(32,64)))
        consumers=rand(64,(32,96))
        work=1+(keys[:,:,None]==consumers[:,None,:]).sum(-1)
        code=keys+64*rand(4,keys.shape)
        p=m(code).softmax(-1)[...,1]
        partner=m(keys+64*rand(4,keys.shape)).softmax(-1)[...,1]
        balance=((p*work).sum(1)/work.sum(1)-.5).square().mean()
        loss=5*balance+(p-partner).square().mean()+.2*(p*(1-p)).mean()
        opt.zero_grad(set_to_none=True);loss.backward();opt.step()
    out.parent.mkdir(parents=True,exist_ok=True);torch.save(m.state_dict(),out)
    out.with_suffix('.json').write_text(json.dumps(dict(seed=seed,steps=512,
        training='synthetic correlated join bags; no real workload labels',
        params=sum(p.numel() for p in m.parameters()),sha256=hashlib.sha256(out.read_bytes()).hexdigest())))


def assignments(path,dev):
    m=RowRouter().to(dev);m.load_state_dict(torch.load(path,map_location='cpu',weights_only=True))
    return m.eval()(torch.arange(256,device=dev)).argmax(-1).int()


if __name__=='__main__':
    q=argparse.ArgumentParser();q.add_argument('out',type=Path);q.add_argument('seed',type=int)
    a=q.parse_args();train(a.out,a.seed)
