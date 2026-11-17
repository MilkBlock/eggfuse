"""Same set/coverage supervision as previous experiment, on causal outputs."""
import sys
from pathlib import Path
import mlx.core as mx
import mlx.nn as nn
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'coverage'))
from objective import penalties
from data import K,V


def objective(model,x,sp,op,rows,length,target):
    out=model(x,sp,op,rows,length);active=target[...,0];value=nn.losses.cross_entropy(out['active_logits'],active,reduction='mean')
    for col in range(2):value+=mx.mean(active*nn.losses.cross_entropy(out['pointer_logits'][:,:,col,:],target[...,col+1],reduction='none'))
    offset=0
    for col,width in enumerate((K,V,V)):
        value+=mx.mean(active*nn.losses.cross_entropy(out['field_logits'][...,offset:offset+width],target[...,col+3],reduction='none'));offset+=width
    coverage,cardinality=penalties(out,target)
    return value+coverage+.25*cardinality
