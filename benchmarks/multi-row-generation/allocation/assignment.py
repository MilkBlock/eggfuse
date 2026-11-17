"""Exact square Hungarian assignment; training-only, no inference dependency."""
import numpy as np


def assign(cost):
    # Vectorized independent batches of the shortest augmenting-path algorithm.
    cost=np.asarray(cost,dtype=np.float64)
    if cost.ndim!=3 or cost.shape[1]!=cost.shape[2] or not np.isfinite(cost).all():
        raise ValueError('finite batched square costs required')
    batch,n,_=cost.shape;g=np.arange(batch);u=np.zeros((batch,n+1));v=u.copy()
    p=np.zeros((batch,n+1),np.int32);way=p.copy()
    for i in range(1,n+1):
        p[:,0]=i;j0=np.zeros(batch,np.int32);minv=np.full((batch,n+1),np.inf);used=np.zeros((batch,n+1),bool);live=np.ones(batch,bool)
        while live.any():
            ids=g[live];used[ids,j0[ids]]=True;i0=p[ids,j0[ids]]
            cur=cost[ids,i0-1,:]-u[ids,i0,None]-v[ids,1:]
            improve=(cur<minv[ids,1:])&~used[ids,1:]
            minv[ids,1:]=np.where(improve,cur,minv[ids,1:]);way[ids,1:]=np.where(improve,j0[ids,None],way[ids,1:])
            available=np.where(used[ids,1:],np.inf,minv[ids,1:]);j1=available.argmin(1)+1;delta=available[np.arange(len(ids)),j1-1]
            for j in range(n+1):
                selected=used[ids,j];gi=ids[selected];u[gi,p[gi,j]]+=delta[selected];v[gi,j]-=delta[selected]
            minv[ids]-=np.where(used[ids],0,delta[:,None]);j0[ids]=j1
            live[ids]=p[ids,j1]!=0
        live=j0!=0
        while live.any():
            ids=g[live];j1=way[ids,j0[ids]];p[ids,j0[ids]]=p[ids,j1];j0[ids]=j1;live=j0!=0
    result=np.empty((batch,n),np.int32)
    for j in range(1,n+1):result[g,p[:,j]-1]=j-1
    return result
