"""Training-only soft coverage constraint. Inference is original SetGenerator."""
import sys
from pathlib import Path
import mlx.core as mx
import mlx.nn as nn
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'allocation'))
from data import N,K,V,Q


def penalties(out,target):
    active=mx.softmax(out['active_logits'],-1)[...,1];pointer=mx.softmax(out['pointer_logits'],-1)
    claims=mx.sum(active[...,None,None]*pointer[:,:,0,:,None]*pointer[:,:,1,None,:],axis=1)
    expected=mx.sum(target[...,0,None,None]*mx.eye(N)[target[...,1]][...,None]*mx.eye(N)[target[...,2]][...,None,:],axis=1)
    count=mx.sum(target[...,0],axis=1)
    coverage=mx.mean(mx.sum(mx.square(claims-expected),axis=(1,2))/mx.maximum(count,1))
    cardinality=mx.mean(mx.square(mx.sum(active,axis=1)-count))/Q
    return coverage,cardinality


def objective(model,x,sp,op,target,strength=1.0):
    out=model(x,sp,op);active=target[...,0];value=nn.losses.cross_entropy(out['active_logits'],active,reduction='mean')
    for col in range(2):value+=mx.mean(active*nn.losses.cross_entropy(out['pointer_logits'][:,:,col,:],target[...,col+1],reduction='none'))
    offset=0
    for col,width in enumerate((K,V,V)):
        value+=mx.mean(active*nn.losses.cross_entropy(out['field_logits'][...,offset:offset+width],target[...,col+3],reduction='none'));offset+=width
    coverage,cardinality=penalties(out,target)
    return value+strength*(coverage+.25*cardinality)
