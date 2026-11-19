"""Shared role pointer. All instance-specific content is gathered through its predicted port."""
import argparse
import hashlib
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F


class PortReader(nn.Module):
    def __init__(self):
        super().__init__()
        self.score=nn.Sequential(nn.Linear(5,16),nn.Tanh(),nn.Linear(16,1))

    def forward(self,width,query,column):
        # query=-1 designates the result; nonnegative queries designate *ordered* input ports.
        # The final candidate is null. Padding alone is masked, not incorrect live ports.
        q=query[:,None];c=column[None,:].expand(len(q),-1);w=width[:,None]
        null=c<0
        features=torch.stack(((q<0).expand_as(c), c==w-1, null, (c-q).abs().float().clamp(max=4),
                              ((q>=w-1)&(q>=0)).expand_as(c)),-1).float()
        return self.score(features).squeeze(-1).masked_fill((c>=w)&~null,-1e8)


def train(out):
    if out.exists():raise FileExistsError(out)
    torch.manual_seed(1703);model=PortReader().to('mps')
    opt=torch.optim.Adam(model.parameters(),lr=.01)
    # Synthetic slot declarations only. No workload facts, IDs, Run logs or labels.
    pairs=torch.cartesian_prod(torch.arange(1,8),torch.arange(-1,9)).to('mps')
    width,query=pairs.T
    columns=torch.arange(-1,9,device='mps')
    wanted=torch.where(query<0,width,torch.where(query<width-1,query+1,0)).long()
    for _ in range(550):
        opt.zero_grad(set_to_none=True);loss=F.cross_entropy(model(width,query,columns),wanted)
        loss.backward();opt.step()
    if not torch.equal(model(width,query,columns).argmax(-1),wanted):raise ValueError('failed role contract')
    out.parent.mkdir(parents=True,exist_ok=True);torch.save(model.state_dict(),out)


def mapping(model,width,dev):
    cols=torch.arange(-1,width,device=dev)
    queries=torch.cat((torch.arange(width-1,device=dev),torch.tensor([-1],device=dev)))
    return cols[model(torch.full_like(queries,width),queries,cols).argmax(-1)]


def load(path,dev):
    model=PortReader();model.load_state_dict(torch.load(path,map_location='cpu',weights_only=True))
    return model.to(dev).eval()


def apply_roles(prog,image,weight,dev,width):
    model=load(weight,dev)
    def array(k):return torch.as_tensor(image[k],device=dev).long()
    span=array('role_width');query=array('role_query')
    cols=torch.arange(-1,width,device=dev)
    selected=cols[model(span,query,cols).argmax(-1)]
    base=array('role_base');dst=array('role_dst');source=base+selected.clamp_min(0)
    return prog.scatter(0,dst,prog[source]),(source==dst).all() & (selected>=0).all()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);args=p.parse_args();train(args.output)
