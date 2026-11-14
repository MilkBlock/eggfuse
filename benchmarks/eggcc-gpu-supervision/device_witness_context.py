"""Bounded forward provenance for existing Cell exports, not consumer lists.

Fixed gathers follow actual matched sources. Depth is a compiled budget, not
proof of global constructor coverage. References never copy slot payloads.
"""
from device_slot_owners import live


def initialize(state,arity,xp):
    out=dict(state);n=len(state['present'])
    for key in ('context_sources','context_generations'):
        out[key]=xp.full((n,arity),-1,xp.int32)
    out['context_valid']=xp.zeros((n,arity),xp.bool_)
    return out


def retain(before,after,batch,index,xp):
    if 'context_sources' not in before:return after
    out=dict(after);written=after['present']&~before['present']
    for key,source in (('context_sources','sources'),('context_generations','generations'),('context_valid','mask')):
        out[key]=xp.where(written[:,None],batch[source][index][None,:],before[key])
    return out


def sources(state,rows,valid,generations,depth,xp):
    all_rows=[];all_valid=[];all_generations=[]
    for step in range(depth+1):
        safe=xp.clip(rows,0,len(state['present'])-1)
        valid=valid&(rows>=0)&(rows<len(state['present']))&state['present'][safe]&state['visible'][safe]&state['settled'][safe]
        valid=valid&(state['generation'][safe]==generations)&live(state,safe,xp)
        all_rows.append(safe);all_valid.append(valid);all_generations.append(generations)
        if step<depth:
            valid=(valid[:,None]&state['context_valid'][safe]).reshape(-1)
            generations=state['context_generations'][safe].reshape(-1)
            rows=state['context_sources'][safe].reshape(-1)
    return tuple(xp.concatenate(v) for v in (all_rows,all_valid,all_generations))
