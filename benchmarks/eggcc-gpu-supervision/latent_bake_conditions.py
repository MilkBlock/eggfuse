"""Compile local energy hints into latent quadratic forms, without port decoding."""
import numpy as np
from boundary_cell_ridge import D,B


def compile_conditions(plan,basis,scale,gain):
    new,pairs=plan;rank=basis.shape[1];forms=np.zeros((2,rank,rank),np.float32)
    selected=np.flatnonzero(new);count=len(selected)
    if count:
        rows=(D+selected[:,None]*B+np.arange(B)[None,:]).reshape(-1)
        decoder=basis[rows].T/scale[rows][None,:]/gain
        forms[0]=decoder@decoder.T/(B*count)
    for left,right in pairs:
        a=D+left*B;b=D+right*B
        delta=(basis[a:a+B].T/scale[a:a+B][None,:]-basis[b:b+B].T/scale[b:b+B][None,:])/gain
        forms[1]+=delta@delta.T/(B*len(pairs))
    return forms,np.array([count,len(pairs)],np.float32)


def energy(z,forms,xp):
    value=xp.sum(xp.matmul(z[:,None,None,:],forms)*z[:,None,None,:],axis=-1)[:,:,0]
    return xp.maximum(value,0)


def hints(z,forms,counts,xp):
    value=energy(z,forms,xp);output=value[:,0];eq=value[:,1];root=xp.sqrt(output)
    count=counts[:,0];pairs=counts[:,1]
    return xp.stack([(count>0).astype(xp.float32),xp.log1p(count),output/(1+output),root/(1+root),xp.tanh(4*output),(pairs>0).astype(xp.float32),xp.log1p(pairs),eq/(1+eq)],axis=1)
