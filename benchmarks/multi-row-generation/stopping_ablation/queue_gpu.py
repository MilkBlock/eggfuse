"""Run an interruptible device-side work queue over generated Pair witnesses."""
from functools import lru_cache
from pathlib import Path
import sys

import torch
from torch import nn

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'union_ablation'))
# The preceding benchmark's local module is also named engine. Import it
# under an explicit name to preserve both standalone entry points.
import importlib.util
spec=importlib.util.spec_from_file_location('union_program',HERE.parent/'union_ablation/engine.py')
prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
from experiment import dataset,study,device,load_producer,upload,digest
from network import produce,read_parent
device_plan=prior.device_plan

POLICIES={'fixed':0,'exact':1,'guard':2,'raw':3,'fair':4}
PANELS=('ordinary','late_union','late_duplicate','late_seal')
MAX_TICKS=48


class Gate(nn.Module):
    def __init__(self):
        super().__init__()
        self.layers=nn.Sequential(nn.Linear(6,12),nn.ReLU(),nn.Linear(12,3))
    def forward(self,x):return self.layers(x)
    def packed(self):return torch.cat([p.detach().flatten() for p in self.parameters()]).contiguous()


@lru_cache(maxsize=1)
def kernel():
    return torch.mps.compile_shader((HERE/'stop.metal').read_text()).advance


def manifest(x,plan,panel,indices):
    """The transport alone owns future payloads and delivery times."""
    if panel not in PANELS and panel!='train':raise ValueError(panel)
    _,vertices,local,_=plan
    req,phase,commit,ext,ep=x[2],x[5],x[6],x[7],x[8];g=len(req)
    events=torch.full((g,2,10),-1,device=req.device,dtype=torch.int32)
    for owner in (0,1):
        on=(phase[:,owner]>=1)&commit[:,owner].bool()
        events[:,0,owner*3:owner*3+2]=torch.where(on[:,None],local[owner],-1)
        events[:,0,owner*3+2]=owner
    ends=torch.stack([vertices[ext[:,j].long(),ep[:,k].long()] for k,j in enumerate((1,3))],-1)
    events[:,1,:2]=torch.where(ext[:,:1].bool(),ends,-1);events[:,1,2]=0
    events[:,:,9]=0
    late=10 if panel!='train' else 3
    # Counterfactual panels preserve the complete source graph. The late
    # retransmission is reflexive and can never add a logical fact.
    if panel in ('ordinary','train'):
        bucket=(indices+3*(indices//8))%16
        events[:,1,2]=torch.where(bucket==0,late,0)
        duplicate=bucket==1
        events[:,1,3:5]=torch.where(duplicate[:,None],local[0,0].expand(g,2),-1)
        events[:,1,5]=late
        events[:,1,9]=torch.where(bucket==2,late,0)
    elif panel=='late_union':events[:,1,2]=late
    elif panel=='late_duplicate':
        events[:,1,3:5]=local[0,0];events[:,1,5]=late
    elif panel=='late_seal':events[:,1,9]=late
    return events


def inputs(model,x,table,plan,panel,indices):
    first,token=produce(model,x,table)
    rows,ptr,ok=read_parent(token,x[2])
    source=torch.cat((torch.where(ok,ptr,-1)[...,None],rows[...,:2],x[2][...,4:5],rows[...,3:5]),-1).int()
    vertices=plan[1];ports=x[4];req=x[2]
    addr=torch.stack((vertices[req[...,0].long(),ports[...,0].long()],vertices[req[...,2].long(),ports[...,1].long()]),-1)
    return first,(manifest(x,plan,panel,indices),plan[0],addr.contiguous(),source.contiguous())


class Queue:
    def __init__(self,batch,n,dev,trace=False):
        self.trace_enabled=trace
        self.classes=torch.arange(n,device=dev,dtype=torch.int32).repeat(batch,1)
        self.index=self.classes.clone()
        def alloc(shape,fill):return torch.full((batch,*shape),fill,dtype=torch.int32,device=dev)
        self.state=alloc((24,),0);self.visible=alloc((3,30),-1)
        self.boundary=alloc((2,8),-1)
        self.trace=alloc((MAX_TICKS,11),-1) if trace else alloc((1,),-1)

    def advance(self,args,gate,mode,k,ticks,blind=False):
        if ticks<1 or k<1:raise ValueError('positive tick budget and slice length required')
        cfg=[POLICIES[mode],k,ticks,int(self.trace_enabled),MAX_TICKS,int(blind)]
        kernel()(self.classes,self.state,*args,gate,self.visible,self.boundary,self.trace,self.index,cfg,
                 threads=len(self.state),arg_casts={11:'int32'})

    def export(self):
        return {k:getattr(self,k).cpu().numpy().copy() for k in ('state','visible','boundary','classes','index')}


def checkpoint(queue,args):
    """Detach a resumable GPU checkpoint, including the transport and completed observers."""
    keys=('classes','index','state','visible','boundary')
    return tuple(getattr(queue,k).clone() for k in keys),tuple(v.clone() for v in args)


def restore(saved):
    tensors,args=saved
    classes,index,state,visible,boundary=tensors
    q=Queue.__new__(Queue)
    q.trace_enabled=False
    q.classes,q.index,q.state,q.visible,q.boundary=classes,index,state,visible,boundary
    q.trace=torch.empty((len(state),1),device=state.device,dtype=state.dtype)
    return q,args


def status(state):
    """Device classification: 0 new phase, 1 runnable, 2 waiting on delivery/seal,
    3 ready for an observer, 4 proved terminal, 5 prematurely declared terminal.
    """
    phase=state[:,0];opened=state[:,8].bool()
    work=(state[:,3]!=0)|(state[:,4]!=0)|(state[:,5]!=0)
    waiting=(state[:,2]!=0)|(state[:,6]==0)
    return torch.where(phase==2,torch.where(state[:,16]==0,4,5),
           torch.where(~opened,0,torch.where(work,1,torch.where(waiting,2,3))))
