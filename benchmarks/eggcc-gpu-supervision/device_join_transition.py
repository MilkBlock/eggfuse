"""Multi-source match -> live features -> ridge -> token admission.

Witnesses remain shared readers. A joint match is not an ownership proof.
"""
import numpy as np
from device_query_join import compile_query,match_inputs
from device_input_features import compile_inputs
from multi_entry_ridge import template,neighborhood_template
from device_ridge_transition import infer
from device_token_commit import commit
from device_slot_owners import shape as slot_shape,has as has_slot,read as read_slot


def compile_transition(recipe,rid,channels=4,views=None,source_relations=False):
    if not 1<=channels<=8:raise ValueError('unsupported channel count')
    query=compile_query(recipe,rid,views)
    if not query['covered'] or not query['atoms']:raise ValueError('nonempty supported constructor query required')
    cr,_=template(recipe['rules'][rid]);origins={}
    for ai,atom in enumerate(query['atoms']):
        for field,slot in enumerate(atom['slots']):origins.setdefault(slot,(ai,field))
    routing=np.random.default_rng(777).normal(0,1/np.sqrt(128),(128,channels-1)).astype(np.float32)
    source_roles={};source_near={};ports=[]
    if source_relations:cn,_=neighborhood_template(recipe['rules'][rid])
    for slot in query['required']:
        if recipe['rules'][rid]['slots'][slot]['sort']['kind']!='eq':continue
        ai,field=origins[slot];view=query['atoms'][ai]['view'];edges=[];routes=[];relations=[]
        for record,source_rule in enumerate(view['rule']):
            if source_rule<0 or not view['supported'][record]:edges.append(np.zeros(128));routes.append(np.zeros(channels));relations.append(np.zeros(128));continue
            if int(source_rule) not in source_roles:source_roles[int(source_rule)]=template(recipe['rules'][source_rule])[0]
            if source_relations:
                if int(source_rule) not in source_near:source_near[int(source_rule)]=neighborhood_template(recipe['rules'][source_rule])[0]
                sr=source_near[int(source_rule)][view['slots'][record,field]]
                relations.append(np.concatenate([np.tanh(cn[slot]+sr),np.tanh(cn[slot]-sr)]))
            role=source_roles[int(source_rule)][view['slots'][record,field]]
            edges.append(np.concatenate([np.tanh(cr[slot]+role),np.tanh(cr[slot]-role)]))
            routes.append(np.concatenate([np.ones(1),np.tanh(3*np.concatenate([cr[slot],role])@routing)]))
        port=dict(slot=slot,atom=ai,edge=np.array(edges,np.float32),route=np.array(routes,np.float32))
        if source_relations:port['source_relation']=np.array(relations,np.float32)
        ports.append(port)
    return dict(query=query,inputs=compile_inputs(recipe['rules'][rid]),ports=ports,channels=channels,
                completed=not recipe['rules'][rid]['effects'],source_relations=source_relations)


def proposals(state,plan,model,capacity,external_complete,eq_settled,xp):
    bindings,features,encoding=match_inputs(state,plan['query'],plan['inputs'],capacity,external_complete,eq_settled,xp)
    sources=[];edges=[];routes=[];generations=[];relations=[]
    for port in plan['ports']:
        slot=port['slot'];record=bindings['witness_records'][:,port['atom']]
        safe=xp.clip(record,0,port['edge'].shape[0]-1)
        sources.append(bindings['source_rows'][:,slot]);generations.append(bindings['source_generations'][:,slot])
        edges.append(port['edge'][safe]);routes.append(port['route'][safe])
        if plan.get('source_relations',False):relations.append(port['source_relation'][safe])
    if sources:
        request=dict(features,sources=xp.stack(sources,axis=1),generations=xp.stack(generations,axis=1),
                     edge=xp.stack(edges,axis=1),route=xp.stack(routes,axis=1),
                     edge_valid=xp.broadcast_to(bindings['live'][:,None],(capacity,len(sources))))
    else:
        request=dict(features,sources=xp.zeros((capacity,1),xp.int32),generations=xp.zeros((capacity,1),xp.int32),
                     edge=xp.zeros((capacity,1,128),xp.float32),route=xp.zeros((capacity,1,plan['channels']),xp.float32),edge_valid=xp.zeros((capacity,1),xp.bool_))
    if plan.get('source_relations',False):
        request['source_relation']=xp.stack(relations,axis=1) if relations else xp.zeros((capacity,1,128),xp.float32)
    tokens,numerical=infer(state,request,model,xp)
    width=slot_shape(state)[1];local=bindings['slots'].shape[1];key_width=state['keys'].shape[1]
    required=plan['query']['required']
    if local>width or len(required)+1>key_width:raise ValueError('instance layout too small')
    key=xp.concatenate([xp.full((capacity,1),plan['query']['rule'],xp.int32),bindings['slots'][:,required],xp.full((capacity,key_width-1-len(required)),-1,xp.int32)],axis=1)
    witness=bindings['witness_rows']
    p=dict(keys=key,tokens=tokens,source=xp.full(capacity,-1,xp.int32),generation=xp.zeros(capacity,xp.int32),
           matched=bindings['live']&numerical['ready'],completed=xp.full(capacity,plan['completed'],xp.bool_),transfer_covered=xp.zeros(capacity,xp.bool_),
           witness_sources=witness,witness_generations=bindings['witness_generations'],witness_valid=xp.broadcast_to(bindings['live'][:,None],witness.shape),
           missing_witness=(bindings['live']&~numerical['ready'])|~bindings['complete'])
    if 'takeover_plan' in state:
        indices=[]
        for ai,index in enumerate(plan.get('takeover_indices',[])):
            record=bindings['witness_records'][:,ai]
            indices.append(xp.where((record>=0)&(record<len(index)),xp.array(index)[xp.clip(record,0,len(index)-1)],-1))
        atoms=state['takeover_plan'].shape[1]
        if witness.shape[1]>atoms:raise ValueError('takeover evidence capacity')
        selected=xp.stack(indices,axis=1) if indices else xp.full(witness.shape,-1,xp.int32)
        for name,value in [('plan',selected),('source',witness),('generation',bindings['witness_generations'])]:
            p['takeover_'+name]=xp.concatenate([value,xp.full((capacity,atoms-value.shape[1]),-1,xp.int32)],axis=1)
    for key in ('slots','slot_roots','slot_valid'):
        p[key]=xp.concatenate([bindings[key],xp.full((capacity,width-local),False if key=='slot_valid' else -1,bindings[key].dtype)],axis=1)
    rows=xp.clip(bindings['source_rows'],0,slot_shape(state)[0]-1);slots=xp.clip(bindings['source_slots'],0,width-1)
    for key in ('scalar_numbers','scalar_numeric','scalar_codes','scalar_valid'):
        if has_slot(state,key):
            value=read_slot(state,key,rows,slots,xp);mask=bindings['slot_valid'][:,:,None] if value.ndim==3 else bindings['slot_valid']
            value=xp.where(mask,value,0);padding=(capacity,width-local)+value.shape[2:]
            p[key]=xp.concatenate([value,xp.zeros(padding,value.dtype)],axis=1)
    return p,dict(query_complete=bindings['complete'],overflow=bindings['overflow'],candidate_lanes=bindings['candidate_lanes'],encoding=encoding,numerical=numerical)


def step(state,plan,model,capacity,external_complete,eq_settled,xp,key_context=None):
    p,marks=proposals(state,plan,model,capacity,external_complete,eq_settled,xp)
    out,admission=commit(state,p,xp,key_context)
    return out,dict(marks,admission=admission)


def run_round(state,blocks,model,stage,xp,capacity=16,external_complete=False,eq_settled=False,key_context=None):
    if not blocks:raise ValueError('empty query catalog is not coverage')
    candidates=[];complete=xp.array(True)
    max_atoms=max(len(plan['query']['atoms']) for _,plan in blocks)
    for stage_id,plan in blocks:
        p,marks=proposals(state,plan,model,capacity,external_complete,eq_settled,xp)
        enabled=stage==stage_id
        p['matched']=p['matched']&enabled;p['missing_witness']=p['missing_witness']&enabled
        complete=complete&(~enabled|marks['query_complete'])
        for key in ('witness_sources','witness_generations','witness_valid'):
            value=p[key];pad=max_atoms-value.shape[1]
            p[key]=xp.concatenate([value,xp.full((capacity,pad),False if key=='witness_valid' else -1,value.dtype)],axis=1)
        candidates.append(p)
    combined={k:xp.concatenate([p[k] for p in candidates],axis=0) for k in candidates[0]}
    out,marks=commit(state,combined,xp,key_context)
    marks['query_complete']=complete;marks['needs_attention']=marks['needs_attention']|~complete
    marks['new_tokens']=xp.sum(marks['accepted'].astype(xp.int32))
    marks['proposed_matches']=xp.sum(combined['matched'].astype(xp.int32))
    return out,marks
