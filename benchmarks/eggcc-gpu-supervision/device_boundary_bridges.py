"""Floating cross-port messages through the same logical neighboring Cell.

Logical Cell co-occurrence is distinct from sharing a physical owner payload.
Only current typed boundary connections are used; no future labels or IDs enter
floating features. This experimental encoder is not installed in the runtime.
"""
import numpy as np
from device_boundary_context import masks


def compile_pairs(plan):
    ports=list(map(int,plan['ports']));p=len(ports);indices=[];valid=[]
    if not p:raise ValueError('bridge needs Eq input ports')
    for a in range(plan['width']):
        for b in range(a+1,plan['width']):
            ok=a in ports and b in ports
            valid.append(ok);indices.append(ports.index(a)*p+ports.index(b) if ok else 0)
    return dict(indices=np.array(indices,np.int32),valid=np.array(valid,bool))


def encode(boundary,bindings,plan,pairs,xp):
    conn,_,safe,valid=masks(boundary,bindings,plan,xp)
    tokens=xp.where(boundary['live'][:,None],boundary['tokens'],0)
    h=xp.tanh((tokens@plan['token_weight'])[:,None,:]+plan['roles'][safe]@plan['role_weight'])
    h=xp.where(valid[:,:,None],h,0)
    # Each row is a logical Cell, even when multiple rows share one physical owner.
    messages=(conn[:,:,:,None,:].astype(xp.float32)@h[None,None,:,:,:]).squeeze(-2)
    z=xp.transpose(messages,(0,3,1,2))
    products=z@xp.swapaxes(z,-1,-2)
    seen=xp.any(conn,axis=-1).astype(xp.float32)
    counts=seen@xp.swapaxes(seen,-1,-2)
    b,p=conn.shape[:2];hidden=h.shape[-1]
    pooled=xp.transpose(products,(0,2,3,1)).reshape(b,p*p,hidden)[:,pairs['indices']]
    count=counts.reshape(b,p*p)[:,pairs['indices']]
    keep=pairs['valid'][None,:]
    out=xp.where(keep[:,:,None],xp.tanh(pooled/xp.sqrt(xp.maximum(count,1))[:,:,None]),0)
    return out.reshape(b,-1),xp.where(keep,count,0)
