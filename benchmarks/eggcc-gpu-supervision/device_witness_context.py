"""Bounded forward provenance for existing Cell exports, not consumer lists.

Fixed gathers follow actual matched sources. Depth is a compiled budget, not
proof of global constructor coverage. References never copy slot payloads.
"""
from device_slot_owners import live


def initialize(state,arity,xp):
    out=dict(state);n=len(state['present'])
    columns=('context_sources','context_generations','context_valid')
    if any(k in state for k in columns):
        if not all(k in state and state[k].shape==(n,arity) for k in columns):
            raise ValueError('source context layout must persist across stages')
        return out
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


def inspect(state,rows,valid,generations,depth,xp):
    all_rows=[];all_valid=[];all_generations=[];invalid=xp.array(False)
    for step in range(depth+1):
        safe=xp.clip(rows,0,len(state['present'])-1)
        available=(rows>=0)&(rows<len(state['present']))&state['present'][safe]&state['visible'][safe]&state['settled'][safe]
        available=available&(state['generation'][safe]==generations)&live(state,safe,xp)
        invalid=invalid|xp.any(valid&~available)
        valid=valid&available
        all_rows.append(safe);all_valid.append(valid);all_generations.append(generations)
        if step<depth:
            valid=(valid[:,None]&state['context_valid'][safe]).reshape(-1)
            generations=state['context_generations'][safe].reshape(-1)
            rows=state['context_sources'][safe].reshape(-1)
    return (*tuple(xp.concatenate(v) for v in (all_rows,all_valid,all_generations)),invalid)


def sources(state,rows,valid,generations,depth,xp):
    return inspect(state,rows,valid,generations,depth,xp)[:3]
