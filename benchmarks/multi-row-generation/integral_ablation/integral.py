"""Incremental Run interface: equality events are delivered only at their source boundary."""
from functools import lru_cache
from pathlib import Path
import sys

import torch

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'union_ablation'))
from engine import device_plan,kernels
from experiment import dataset,study,device,load_producer,upload,produce
from network import read_parent

MODES={'source':0,'primary':1,'integral':2,'unchecked':3,'early_public':4,'learned_integral':2,'stable_integral':5}


@lru_cache(maxsize=1)
def library():
    return torch.mps.compile_shader((HERE/'members.metal').read_text())


def ingress(model,x,table,mode):
    first,token=produce(model,x,table)
    req=x[2];rows,ptr,exists=read_parent(token,req)
    projected=torch.cat((torch.where(exists,ptr,-1)[...,None],rows,req[...,4:5]),-1)
    admission=torch.ones_like(ptr,dtype=torch.int32)
    if mode=='learned_integral':
        # Stage A exposes neither local commit nor any external edge. No future
        # tensor values are passed to the frozen consumer head.
        rq,phase,commit,event,ends=x[4:]
        controls=[torch.zeros_like(v) for v in (phase,commit,event,ends)]
        cond=model.operand[1][None].expand(len(req),-1,-1)
        proposals,_=model.resume(token,req,rq,*controls,table,cond)
        p=proposals['pointers']
        request_id=torch.arange(4,device=req.device)[None,:,None]
        admission=((p[:,None,:,1]==request_id)&(p[:,None,:,0]==ptr[...,None])
                   &proposals['active'][:,None,:].bool()).any(-1).int()
    return first,projected.int().contiguous(),admission.contiguous()


class Arena:
    def __init__(self,x,plan,*,fixed=False):
        self.words,self.nodes,self.local,size=plan
        req,ports=x[2],x[4];batch=len(req);dev=req.device
        self.batch=batch
        self.address=torch.stack((self.nodes[req[...,0].long(),ports[...,0].long()],
                                  self.nodes[req[...,2].long(),ports[...,1].long()]),-1).contiguous()
        self.classes=torch.arange(size,device=dev,dtype=torch.int32).repeat(batch,1)
        def alloc(shape,value):
            return torch.full((batch,*shape),value,dtype=torch.int32,device=dev)
        self.book=alloc((23,),0);self.ref=alloc((16,),-1);self.pages=[];self.dummy=alloc((1,),-1);self.fixed=fixed
        self.stats=alloc((24,),0);self.empty=alloc((2,),-1)
        self.obs=alloc((10,),0);self.pub=alloc((16,14),-1)

    def step(self,stage,x,inputs,admission,mode):
        if stage==0:
            events=self.empty;count=1
        elif stage==1:
            on=(x[5]>=1)&x[6].bool()
            events=torch.where(on[...,None],self.local[None],self.empty[:,None]);count=2
        else:
            ext,ends=x[-2:]
            sides=[self.nodes[ext[:,j].long(),ends[:,i].long()] for i,j in enumerate((1,3))]
            events=torch.where(ext[:,:1].bool(),torch.stack(sides,-1),self.empty);count=1
        kernels().advance(self.classes,self.book,events.contiguous(),self.address,self.words,self.obs,3,count,
                          threads=self.batch,arg_casts={6:'int32',7:'int32'})
        capacities={'source':(4,12,16),'primary':(8,16,16)}
        capacity=16 if self.fixed else capacities.get(mode,(16,16,16))[stage]
        while len(self.pages)*4<capacity:
            self.pages.append(torch.full((self.batch,4,14),-1,dtype=torch.int32,device=self.pub.device))
        page_args=self.pages+[self.dummy]*(4-len(self.pages))
        library().saturate(inputs,self.obs,admission,self.ref,*page_args,self.stats,self.pub,
                           stage,MODES[mode],capacity,threads=self.batch,arg_casts={10:'int32',11:'int32',12:'int32'})

    def snapshot(self):
        snapshot={k:getattr(self,k).clone() for k in ('ref','stats','obs','pub')}
        pages=self.pages+[torch.full_like(self.pages[0],-1)]*(4-len(self.pages))
        snapshot['pool']=torch.cat(pages,dim=1)
        return snapshot


def run(x,plan,inputs,admission,mode,trace=False):
    arena=Arena(x,plan);frames=[]
    for stage in range(3):
        arena.step(stage,x,inputs,admission,mode)
        if trace:frames.append(arena.snapshot())
    return arena,frames
