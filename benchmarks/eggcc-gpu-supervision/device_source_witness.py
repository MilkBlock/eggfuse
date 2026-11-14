"""Reuse constructor witnesses only from the already matched source Cells.

Bake enumerates possible export sites; GPU compares their operands against the
new frame. No graph-wide table lookup or producer consumer lists are created.
Failure to find a witness is not proof that the result is globally fresh.
"""
import numpy as np
from device_witness_views import compile_view
from device_slot_owners import read
from typed_literal import compiled_id


def compile_sites(recipe, rule):
    tables={t['name']:(i,t) for i,t in enumerate(recipe['tables'])}
    sites={}
    for op in rule['effects']:
        if op['kind']!='construct':continue
        ti,table=tables[op['call']['table']]
        if table['kind']!='constructor':continue
        sites[op['dst']]=dict(view=compile_view(recipe,ti,len(op['args'])),
            slots=np.array([a.get('slot',0) for a in op['args']],np.int32),
            literals=np.array([-1 if 'slot' in a else compiled_id(a,recipe) for a in op['args']],np.int32))
    return sites


def lookup(state, payload, batch, index, site, xp):
    """Inspect fixed export sites of selected inputs, preserving stable IDs."""
    v={k:xp.array(a) if isinstance(a,np.ndarray) else a for k,a in site['view'].items()}
    sources=batch['sources'][index];row=sources[:,None,None]
    positions=v['slots'][None,:,:];constant=v['literal_ids'][None,:,:]>=0
    slots=xp.where(constant,v['literal_ids'][None,:,:],read(state,'slots',row,positions,xp))
    roots=xp.where(constant,v['literal_ids'][None,:,:],read(state,'slot_roots',row,positions,xp))
    valid=constant|read(state,'slot_valid',row,positions,xp)
    pc=xp.where(state['settled'][sources,None],v['effect_count'][None,:],state['effect_pc'][sources,None])
    live=(batch['mask'][index,:,None]&state['present'][sources,None]&state['visible'][sources,None]
          &state['settled'][sources,None]&(state['generation'][sources,None]==batch['generations'][index,:,None])
          &(state['keys'][sources,0,None]==v['rule'][None,:])&v['supported'][None,:]
          &(pc>=v['after'][None,:])&(pc<v['expires'][None,:])&xp.all(valid,axis=-1))
    args=xp.where(xp.array(site['literals'])>=0,xp.array(site['literals']),payload['slot_roots'][0,xp.array(site['slots'])])
    args_valid=(xp.array(site['literals'])>=0)|payload['slot_valid'][0,xp.array(site['slots'])]
    matched=live&xp.all(roots[:,:,:-1]==args,axis=-1)&xp.all(args_valid)
    flat=matched.reshape(-1);pick=xp.argmax(flat.astype(xp.int32))
    return xp.any(flat),slots[:,:,-1].reshape(-1)[pick],roots[:,:,-1].reshape(-1)[pick]
