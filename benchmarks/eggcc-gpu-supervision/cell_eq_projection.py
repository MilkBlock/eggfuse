"""Static output projection for proven input-port unions in conditional Cells.

Averaging preserves equality of channels, not the full meaning of the Cell token.
No new union is inferred from floating-point similarity.
"""
import numpy as np
from boundary_cell_ridge import D,B


def groups(pairs):
    components=[]
    for a,b in pairs:
        if a==b:continue
        merged={a,b};rest=[]
        for group in components:
            if group & merged:merged|=group
            else:rest.append(group)
        components=rest+[merged]
    return sorted([sorted(g) for g in components],key=lambda g:g[0])


def compile_projection(plans,capacity):
    families=[groups(pairs) for _,pairs in plans]
    width=max(1,max(sum(map(len,gs)) for gs in families));members=max(1,max((len(g) for gs in families for g in gs),default=1))
    dest=np.zeros((len(plans),width),np.int32);source=np.zeros((len(plans),width,members),np.int32);weights=np.zeros_like(source,dtype=np.float32)
    for i,gs in enumerate(families):
        assigned={p for g in gs for p in g};rows=[(p,g) for g in gs for p in g]
        rows.extend((p,[p]) for p in range(capacity) if p not in assigned)
        for j,(p,g) in enumerate(rows[:width]):
            dest[i,j]=p;source[i,j,:len(g)]=g;weights[i,j,:len(g)]=1/len(g)
    return dest,source,weights


def project(values,wiring,xp):
    dest,source,weights=wiring;channels=values[:,D:].reshape(len(values),-1,B)
    selected=xp.take_along_axis(channels,source.reshape(len(values),-1)[:,:,None],axis=1).reshape(*source.shape,B)
    merged=xp.sum(selected*weights[:,:,:,None],axis=2)
    if xp is np:
        output=channels.copy();np.put_along_axis(output,dest[:,:,None],merged,axis=1)
    else:output=xp.put_along_axis(channels,dest[:,:,None],merged,axis=1)
    return xp.concatenate([values[:,:D],output.reshape(len(values),-1)],axis=1)
