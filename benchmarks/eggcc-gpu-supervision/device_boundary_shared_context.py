"""Fixed floating context propagation through shared boundary Eq ports.

Bounded typed-root scatter avoids quadratic adjacency; the reference fallback
is quadratic in boundary slot capacity. No runtime speed claim.
Exact typed IDs form connectivity only. No future completion labels are read.
"""
import numpy as np
from device_boundary_context import masks


def encode(boundary,bindings,plan,pairs,xp):
    conn,_,safe,valid=masks(boundary,bindings,plan,xp)
    if plan.get('local_context',False):
        port_flow=plan['flow_sorts'][plan['port_sorts']]
        attached=xp.any(conn&port_flow[None,:,None,None],axis=(1,3))
        conn=conn&attached[:,None,:,None]
    tokens=xp.where(boundary['live'][:,None],boundary['tokens'],0)
    h=xp.tanh((tokens@plan['token_weight'])[:,None,:]+plan['roles'][safe]@plan['role_weight'])
    h=xp.where(valid[:,:,None],h,0)
    n,w,d=h.shape
    def denominator(count):
        count=xp.maximum(count,1)
        return count.astype(xp.float32) if plan.get('mean_context',False) else xp.sqrt(count)
    roots=boundary['slot_roots'].reshape(-1);sorts=plan['sorts'][safe].reshape(-1);live=valid.reshape(-1)
    flow=plan['flow_sorts'][xp.clip(sorts,0,len(plan['flow_sorts'])-1)] if plan.get('local_context',False) else xp.ones_like(live)
    if 'root_capacity' in plan:
        capacity=plan['root_capacity'];sort_count=plan['sort_capacity']
        in_range=(roots>=0)&(roots<capacity)&(sorts>=0)&(sorts<sort_count)
        usable=live&flow&in_range
        address=xp.clip(roots,0,capacity-1)*sort_count+xp.clip(sorts,0,sort_count-1)
        values=xp.where(usable[:,None],h.reshape(-1,d),0)
        counts=usable.astype(xp.float32)
        if xp is np:
            total=np.zeros((capacity*sort_count,d),np.float32);number=np.zeros(capacity*sort_count,np.float32)
            np.add.at(total,address,values);np.add.at(number,address,counts)
        else:
            total=xp.zeros((capacity*sort_count,d),xp.float32).at[address].add(values)
            number=xp.zeros(capacity*sort_count,xp.float32).at[address].add(counts)
        shared=total[address]/denominator(number[address])[:,None]
        # Out-of-range live roots must reject the numeric prediction, not alias.
        shared=xp.where(xp.any(live&~in_range),float('nan'),shared)
    else:
        links=(roots[:,None]==roots[None,:])&(sorts[:,None]==sorts[None,:])&live[:,None]&live[None,:]&flow[:,None]&flow[None,:]
        weight=links.astype(xp.float32)
        shared=(weight@h.reshape(-1,d))/denominator(weight.sum(axis=1))[:,None]
    enriched=xp.tanh(h+shared.reshape(n,w,d))
    enriched=xp.where(valid[:,:,None],enriched,0)
    # All ports of a Cell contribute to its context, including ports that are
    # not themselves attached to the current query.
    cell=enriched.sum(axis=1)/denominator(valid.sum(axis=1))[:,None]
    h=xp.where(valid[:,:,None],xp.tanh(enriched+cell[:,None,:]),0).reshape(-1,d)
    count=conn.astype(xp.float32).sum(axis=(-2,-1))
    pooled=conn.reshape(conn.shape[0],conn.shape[1],-1).astype(xp.float32)@h
    pooled=xp.tanh(pooled/denominator(count)[:,:,None])
    slots=xp.arange(plan['width'])[:,None]==plan['ports'][None,:]
    return (slots.astype(xp.float32)[None,:,:]@pooled).reshape(conn.shape[0],-1),count
