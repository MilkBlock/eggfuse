"""Reuse constructor witnesses only from the already matched source Cells.

Bake enumerates possible export sites; GPU compares their operands against the
new frame. No graph-wide table lookup or producer consumer lists are created.
Failure to find a witness is not proof that the result is globally fresh.
"""
import numpy as np
from device_witness_views import compile_view
from device_slot_owners import read
from typed_literal import compiled_id


def group_view(view, rule_count):
    groups=[np.flatnonzero(view['rule']==rid) for rid in range(rule_count)]
    width=max(1,max(map(len,groups),default=0))
    grouped={}
    for name,value in view.items():
        if not isinstance(value,np.ndarray):continue
        array=np.zeros((rule_count,width)+value.shape[1:],dtype=value.dtype)
        if name in ('rule','literal_ids'):array.fill(-1)
        for rid,indices in enumerate(groups):array[rid,:len(indices)]=value[indices]
        grouped[name]=array
    return grouped,width


def compile_sites(recipe, rule):
    tables={t['name']:(i,t) for i,t in enumerate(recipe['tables'])}
    sites={};views={}
    for op in rule['effects']:
        if op['kind']!='construct':continue
        ti,table=tables[op['call']['table']]
        if table['kind']!='constructor':continue
        key=(ti,len(op['args']))
        if key not in views:views[key]=group_view(compile_view(recipe,*key),len(recipe['rules']))
        view,lanes=views[key]
        sites[op['dst']]=dict(view=view,records_per_source=lanes,
            slots=np.array([a.get('slot',0) for a in op['args']],np.int32),
            literals=np.array([-1 if 'slot' in a else compiled_id(a,recipe) for a in op['args']],np.int32))
    return sites


def lookup(state, payload, batch, index, site, xp):
    """Inspect fixed export sites of selected inputs, preserving stable IDs."""
    sources=batch['sources'][index];row=sources[:,None,None]
    template=state['keys'][sources,0]
    rule_count=site['view']['rule'].shape[0]
    known=(template>=0)&(template<rule_count)
    selected=xp.clip(template,0,rule_count-1)
    v={k:xp.array(a)[selected] for k,a in site['view'].items()}
    positions=v['slots'];constant=v['literal_ids']>=0
    slots=xp.where(constant,v['literal_ids'],read(state,'slots',row,positions,xp))
    roots=xp.where(constant,v['literal_ids'],read(state,'slot_roots',row,positions,xp))
    valid=constant|read(state,'slot_valid',row,positions,xp)
    pc=xp.where(state['settled'][sources,None],v['effect_count'],state['effect_pc'][sources,None])
    live=(batch['mask'][index,:,None]&state['present'][sources,None]&state['visible'][sources,None]
          &state['settled'][sources,None]&(state['generation'][sources,None]==batch['generations'][index,:,None])
          &known[:,None]&(template[:,None]==v['rule'])&v['supported']
          &(pc>=v['after'])&(pc<v['expires'])&xp.all(valid,axis=-1))
    args=xp.where(xp.array(site['literals'])>=0,xp.array(site['literals']),payload['slot_roots'][0,xp.array(site['slots'])])
    args_valid=(xp.array(site['literals'])>=0)|payload['slot_valid'][0,xp.array(site['slots'])]
    matched=live&xp.all(roots[:,:,:-1]==args,axis=-1)&xp.all(args_valid)
    flat=matched.reshape(-1);pick=xp.argmax(flat.astype(xp.int32))
    return xp.any(flat),slots[:,:,-1].reshape(-1)[pick],roots[:,:,-1].reshape(-1)[pick]
