from functools import lru_cache
import json
from pathlib import Path

import torch

from actor import choose,joint_choices

HERE=Path(__file__).resolve().parent


@lru_cache(maxsize=1)
def library():
    return torch.mps.compile_shader((HERE/'transfer.metal').read_text())


def device_layout(dev):
    plan=json.loads((HERE/'plan.json').read_text())
    packed=[v for pair in plan['boundary_sources'] for v in pair]
    packed += [v for view in plan['field_views'] for v in view]
    return torch.tensor(packed+plan['record_ports'],device=dev,dtype=torch.int32)


class Arena:
    def __init__(self,token,layout,mode):
        self.source=token.contiguous().clone()
        self.layout=layout; self.mode=mode
        size,dev=len(token),token.device
        self.headers=torch.full((size,8,5),-1,dtype=torch.int32,device=dev)
        self.headers[...,0]=1
        self.targets=torch.zeros((size,2,3),dtype=torch.int32,device=dev)
        self.residual=torch.zeros((size,2,2,51),device=dev)
        self.boundary=torch.zeros((size,2,8),dtype=torch.int32,device=dev)
        self.log=torch.zeros((size,2,2,3),dtype=torch.int32,device=dev)

    def commit(self,scores,pairs,assignments):
        joint=self.mode in ('forward_joint','exact_joint')
        for round_id in range(1 if joint or self.mode=='no_retry' else 2):
            free=None if round_id==0 else self.headers[...,2]<0
            actions=joint_choices(scores,pairs,assignments) if joint else choose(scores,pairs,free)
            code={'retain':0,'unguarded':2}.get(self.mode,1)
            library().commit(self.source,self.headers,self.residual,self.boundary,self.targets,
                             actions,self.log,self.layout,round_id,code,threads=len(scores),
                             arg_casts={8:'int32',9:'int32'})

    def resolve(self,slots,generations):
        refs=torch.stack((slots,generations),-1).int().contiguous()
        size,width=slots.shape
        token=torch.empty((size,width,56),device=slots.device)
        status=torch.empty((size,width),device=slots.device,dtype=torch.int32)
        library().resolve(self.source,self.headers,self.residual,self.boundary,self.targets,
                          refs,self.layout,token,status,width,int(self.mode=='blind'),
                          threads=size*width,arg_casts={9:'int32',10:'int32'})
        return token,status
