"""Separate row, token-position and port rotation axes for temporary reference keys."""
import numpy as np
import mlx.core as mx
AXIS_WIDTH=32
WIDTH=3*AXIS_WIDTH
FREQ=mx.array(np.exp(-np.log(10000.)*np.arange(AXIS_WIDTH//2)/(AXIS_WIDTH//2)),mx.float32)
BASE=mx.ones((WIDTH,),mx.float32)/np.sqrt(WIDTH)

def rotate(x,coordinate,axis,inverse=False):
    begin=axis*AXIS_WIDTH;part=x[...,begin:begin+AXIS_WIDTH]
    phase=coordinate.astype(mx.float32)[...,None]*FREQ*(-1 if inverse else 1)
    a,b=part[...,0::2],part[...,1::2]
    changed=mx.stack((mx.cos(phase)*a-mx.sin(phase)*b,mx.sin(phase)*a+mx.cos(phase)*b),-1).reshape(part.shape)
    return mx.concatenate((x[...,:begin],changed,x[...,begin+AXIS_WIDTH:]),-1)

def key(coordinates):
    out=mx.broadcast_to(BASE,coordinates.shape[:-1]+(WIDTH,))
    for axis in range(3):out=rotate(out,coordinates[...,axis],axis)
    return out

def rebase(encoded,old,new):
    for axis in range(3):
        encoded=rotate(encoded,old[...,axis],axis,True)
        encoded=rotate(encoded,new[...,axis],axis)
    return encoded

def select(query,candidates,valid):
    """Joint coordinate retrieval; generation/visibility are checked by the view resolver."""
    scores=query@mx.swapaxes(key(candidates),-1,-2)
    scores=mx.where(valid[None,:],scores,-mx.inf)
    index=mx.argmax(scores,-1)
    return candidates[index],mx.any(valid)
