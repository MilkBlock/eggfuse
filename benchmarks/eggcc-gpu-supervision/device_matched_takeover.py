"""Matched-source payload takeover at a sealed Run boundary.

Only source addresses/generations and a static plan index survive admission.
Logical facts and tokens stay live; this does not retire activation or readers.
"""
import numpy as np
from device_slot_owners import compile_transfer,transfer

COLUMNS=('takeover_plan','takeover_source','takeover_generation')


def compile_catalog(recipe,blocks,width):
    catalog=[];compiled=[];max_atoms=max(len(p['query']['atoms']) for _,p in blocks)
    for stage,plan in blocks:
        rid=plan['query']['rule'];rule=recipe['rules'][rid]
        inputs=[i for i,s in enumerate(rule['slots']) if s['definition']=='query']
        origins={}
        for ai,atom in enumerate(plan['query']['atoms']):
            for field,slot in enumerate(atom['slots']):origins.setdefault(slot,(ai,field))
        indices=[]
        for ai,atom in enumerate(plan['query']['atoms']):
            view=atom['view'];index=np.full(len(view['rule']),-1,np.int32)
            for record,producer in enumerate(view['rule']):
                if producer<0 or not view['supported'][record]:continue
                projection=[];valid=[]
                for slot in inputs:
                    origin=origins.get(slot)
                    owns=origin is not None and origin[0]==ai
                    projection.append(int(view['slots'][record,origin[1]]) if owns else 0);valid.append(owns)
                candidate=compile_transfer(recipe,dict(producer=int(producer),consumer=rid,projection=projection,projection_valid=valid),width)
                if candidate['covered']:
                    index[record]=len(catalog);catalog.append(candidate)
            indices.append(index)
        compiled.append((stage,dict(plan,takeover_indices=indices)))
    return compiled,catalog,max_atoms


def initialize(state,max_atoms):
    if 'slot_owner' not in state:raise ValueError('physical owner storage required')
    return dict(state,takeover_target_generation=np.full(len(state['present']),-1,np.int32),
                **{k:np.full((len(state['present']),max_atoms),-1,np.int32) for k in COLUMNS})


def finish(state,catalog,boundary,xp,budget=None,diagnostics=False):
    """Static bounded sweep; no CPU value reads or per-source subscriber lists."""
    out=dict(state);attempted=xp.array(0,xp.int32);released=xp.array(0,xp.int32);copied=xp.array(0,xp.int32)
    reasons={k:xp.array(0,xp.int32) for k in ('stale','value_mismatch','uncovered_alias','occupied_destination','epoch_exhausted')} if diagnostics else {}
    quiescent=boundary&~xp.any(state['readers'])
    n,atoms=state['takeover_plan'].shape
    limit=n if budget is None else min(n,budget)
    if limit<1:raise ValueError('positive takeover target budget required')
    eligible=quiescent&state['present']&state['settled']&xp.any(state['takeover_plan']>=0,axis=1)
    targets=xp.sort(xp.where(eligible,xp.arange(n),n))[:limit]
    consumed=xp.zeros(n,xp.bool_)
    tables={k:xp.array(np.array([p[k] for p in catalog])) for k in ('producer','consumer','projection','required','copied','alias')} if catalog else {}
    for lane in range(limit):
        address=targets[lane];target=xp.minimum(address,n-1)
        valid_target=address<n
        consumed=consumed|((xp.arange(n)==target)&valid_target)
        for atom in range(atoms):
            index=state['takeover_plan'][target,atom]
            selected=valid_target&(index>=0)
            if catalog:  # Static catalog shape, not a device control branch.
                enabled=selected&(index<len(catalog))
                plan=dict(covered=True,**{k:v[xp.clip(index,0,len(catalog)-1)] for k,v in tables.items()})
                out,marks=transfer(out,plan,state['takeover_source'][target,atom],xp.array(target),
                    state['takeover_generation'][target,atom],state['takeover_target_generation'][target],enabled,xp)
                attempted=attempted+enabled.astype(xp.int32)
                released=released+marks['released_rows'];copied=copied+marks['copied_fields']
                for key in reasons:reasons[key]=reasons[key]+(enabled&~marks['transferred']&marks[key]).astype(xp.int32)
    # One-shot optional compression. Failed plans leave all semantic state live.
    # Busy readers postpone the attempt and keep evidence for a later boundary.
    for key in COLUMNS:out[key]=xp.where(consumed[:,None],-1,state[key])
    out['takeover_target_generation']=xp.where(consumed,-1,state['takeover_target_generation'])
    result=dict(attempted=attempted,released=released,copied_fields=copied,blocked=attempted-released)
    if diagnostics:result['blocked_reasons']=reasons
    return out,result
