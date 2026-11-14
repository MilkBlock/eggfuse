"""Fixed floating context propagation through shared boundary Eq ports.

Prototype cost is quadratic in boundary slot capacity; no runtime speed claim.
Exact typed IDs form connectivity only. No future completion labels are read.
"""
from device_boundary_context import masks


def encode(boundary,bindings,plan,pairs,xp):
    conn,_,safe,valid=masks(boundary,bindings,plan,xp)
    tokens=xp.where(boundary['live'][:,None],boundary['tokens'],0)
    h=xp.tanh((tokens@plan['token_weight'])[:,None,:]+plan['roles'][safe]@plan['role_weight'])
    h=xp.where(valid[:,:,None],h,0)
    n,w,d=h.shape
    roots=boundary['slot_roots'].reshape(-1);sorts=plan['sorts'][safe].reshape(-1);live=valid.reshape(-1)
    links=(roots[:,None]==roots[None,:])&(sorts[:,None]==sorts[None,:])&live[:,None]&live[None,:]
    weight=links.astype(xp.float32)
    shared=(weight@h.reshape(-1,d))/xp.sqrt(xp.maximum(weight.sum(axis=1),1))[:,None]
    enriched=xp.tanh(h+shared.reshape(n,w,d))
    enriched=xp.where(valid[:,:,None],enriched,0)
    # All ports of a Cell contribute to its context, including ports that are
    # not themselves attached to the current query.
    cell=enriched.sum(axis=1)/xp.sqrt(xp.maximum(valid.sum(axis=1),1))[:,None]
    h=xp.where(valid[:,:,None],xp.tanh(enriched+cell[:,None,:]),0).reshape(-1,d)
    count=conn.astype(xp.float32).sum(axis=(-2,-1))
    pooled=conn.reshape(conn.shape[0],conn.shape[1],-1).astype(xp.float32)@h
    pooled=xp.tanh(pooled/xp.sqrt(xp.maximum(count,1))[:,:,None])
    slots=xp.arange(plan['width'])[:,None]==plan['ports'][None,:]
    return (slots.astype(xp.float32)[None,:,:]@pooled).reshape(conn.shape[0],-1),count
