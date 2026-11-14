"""Multi-source match -> live features -> ridge -> token admission.

Witnesses remain shared readers. A joint match is not an ownership proof.
"""
import numpy as np
from device_query_join import compile_query,match_inputs
from device_input_features import compile_inputs
from device_semantic_template import template,neighborhood_template
from device_ridge_transition import infer,encode_features
from device_token_commit import commit
from device_slot_owners import shape as slot_shape,has as has_slot,read as read_slot


def compile_transition(recipe,rid,channels=4,views=None,source_relations=False,owner_relations=False):
    if not 1<=channels<=8:raise ValueError('unsupported channel count')
    query=compile_query(recipe,rid,views)
    if not query['covered'] or not query['atoms']:raise ValueError('nonempty supported constructor query required')
    cr,_=template(recipe['rules'][rid]);origins={}
    for ai,atom in enumerate(query['atoms']):
        for field,slot in enumerate(atom['slots']):origins.setdefault(slot,(ai,field))
    routing=np.random.default_rng(777).normal(0,1/np.sqrt(128),(128,channels-1)).astype(np.float32)
    source_roles={};source_near={};ports=[]
    if source_relations or owner_relations:cn,_=neighborhood_template(recipe['rules'][rid])
    for slot in query['required']:
        if recipe['rules'][rid]['slots'][slot]['sort']['kind']!='eq':continue
        ai,field=origins[slot];view=query['atoms'][ai]['view'];edges=[];routes=[];relations=[]
        for record,source_rule in enumerate(view['rule']):
            if source_rule<0 or not view['supported'][record]:edges.append(np.zeros(128));routes.append(np.zeros(channels));relations.append(np.zeros(128));continue
            if int(source_rule) not in source_roles:source_roles[int(source_rule)]=template(recipe['rules'][source_rule])[0]
            if source_relations or owner_relations:
                if int(source_rule) not in source_near:source_near[int(source_rule)]=neighborhood_template(recipe['rules'][source_rule])[0]
                sr=source_near[int(source_rule)][view['slots'][record,field]]
                relations.append(np.concatenate([np.tanh(cn[slot]+sr),np.tanh(cn[slot]-sr)]))
            role=source_roles[int(source_rule)][view['slots'][record,field]]
            edges.append(np.concatenate([np.tanh(cr[slot]+role),np.tanh(cr[slot]-role)]))
            routes.append(np.concatenate([np.ones(1),np.tanh(3*np.concatenate([cr[slot],role])@routing)]))
        port=dict(slot=slot,atom=ai,edge=np.array(edges,np.float32),route=np.array(routes,np.float32))
        if source_relations or owner_relations:port['source_relation']=np.array(relations,np.float32)
        ports.append(port)
    return dict(query=query,inputs=compile_inputs(recipe['rules'][rid]),ports=ports,channels=channels,
                completed=not recipe['rules'][rid]['effects'],source_relations=source_relations,owner_relations=owner_relations)


def proposals(state,plan,model,capacity,external_complete,eq_settled,xp,capture=False,boundary_cache=None):
    bindings,features,encoding=match_inputs(state,plan['query'],plan['inputs'],capacity,external_complete,eq_settled,xp)
    sources=[];edges=[];routes=[];generations=[];relations=[]
    for port in plan['ports']:
        slot=port['slot'];record=bindings['witness_records'][:,port['atom']]
        safe=xp.clip(record,0,port['edge'].shape[0]-1)
        sources.append(bindings['source_rows'][:,slot]);generations.append(bindings['source_generations'][:,slot])
        edges.append(port['edge'][safe]);routes.append(port['route'][safe])
        if plan.get('source_relations',False) or plan.get('owner_relations',False):relations.append(port['source_relation'][safe])
    if sources:
        request=dict(features,sources=xp.stack(sources,axis=1),generations=xp.stack(generations,axis=1),
                     edge=xp.stack(edges,axis=1),route=xp.stack(routes,axis=1),
                     edge_valid=xp.broadcast_to(bindings['live'][:,None],(capacity,len(sources))))
    else:
        request=dict(features,sources=xp.zeros((capacity,1),xp.int32),generations=xp.zeros((capacity,1),xp.int32),
                     edge=xp.zeros((capacity,1,128),xp.float32),route=xp.zeros((capacity,1,plan['channels']),xp.float32),edge_valid=xp.zeros((capacity,1),xp.bool_))
    if plan.get('source_relations',False):
        request['source_relation']=xp.stack(relations,axis=1) if relations else xp.zeros((capacity,1,128),xp.float32)
    if plan.get('owner_relations',False):
        request['owner_relation']=xp.stack(relations,axis=1) if relations else xp.zeros((capacity,1,128),xp.float32)
    boundary_capture=None
    base_width=1+model['w'].shape[0]+model['w'].shape[1]
    classifier=plan.get('completion_classifier')
    from device_completion_classifier import input_width
    expected_width=input_width(classifier['head']) if classifier is not None else model['coef'].shape[0]
    if 'joint_projection' in plan:expected_width-=plan['joint_projection'].shape[1]
    if expected_width!=base_width:
        if 'boundary_context' not in plan:raise ValueError('boundary model requires compiled context')
        from device_boundary_context import snapshot,encode,prepare
        group=plan.get('boundary_group')
        cached=boundary_cache.get(group) if boundary_cache is not None and group is not None else None
        if cached is None:
            boundary=snapshot(state,xp)
            raw=prepare(boundary,plan['boundary_context'],xp)
            cached=dict(boundary=boundary,raw=raw)
            if plan.get('shared_boundary_context',False):
                from device_boundary_shared_context import prepare as prepare_shared
                cached['shared']=prepare_shared(boundary,plan['boundary_context'],xp,raw)
            if boundary_cache is not None and group is not None:boundary_cache[group]=cached
        boundary=cached['boundary']
        extra,counts=encode(boundary,bindings,plan['boundary_context'],xp,prepared=cached['raw'])
        context_width=0
        if plan.get('shared_boundary_context',False):
            if classifier is None:raise ValueError('shared context requires classifier')
            from device_boundary_shared_context import encode as shared_encode
            shared,_=shared_encode(boundary,bindings,plan['boundary_context'],None,xp,prepared=cached['shared'])
            request['shared_boundary_features']=shared;context_width=shared.shape[1]
            if 'root_capacity' in plan['boundary_context']:
                request['shared_root_capacity']=xp.array(plan['boundary_context']['root_capacity'])
                request['shared_sort_capacity']=xp.array(plan['boundary_context']['sort_capacity'])
        if expected_width!=base_width+extra.shape[1]+context_width:raise ValueError('boundary model width mismatch')
        request['boundary_features']=extra
        boundary_capture=dict(boundary=boundary,boundary_features=extra,boundary_counts=counts)
    if classifier is not None:
        if 'completion_readout' in plan:raise ValueError('choose one completion predictor')
        classifier_features,numerical=encode_features(state,request,model,xp)
        if 'shared_boundary_features' in request:
            classifier_features=xp.concatenate([classifier_features,request['shared_boundary_features']],axis=1)
        if 'joint_projection' in plan:
            from device_joint_features import expand
            classifier_features=expand(classifier_features,plan['joint_projection'],xp)
            request['joint_features']=xp.array(True)
        tokens=None  # Filled directly by the state head after scalar slots are available.
    else:tokens,numerical=infer(state,request,model,xp)
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
    completion_readout=None
    if classifier is not None or 'completion_readout' in plan:
        from device_completion_readout import scalar_inputs
        if classifier is not None:
            from device_completion_classifier import apply
            codes,scalar_ready=scalar_inputs(p,classifier,xp)
            tokens,completion_readout=apply(classifier_features,bindings,codes,scalar_ready,classifier,xp)
        else:
            from device_completion_readout import apply
            codes,scalar_ready=scalar_inputs(p,plan['completion_readout'],xp)
            tokens,completion_readout=apply(tokens,bindings,codes,scalar_ready,plan['completion_readout'],xp)
        p['tokens']=tokens
        p['missing_witness']=p['missing_witness']|(bindings['live']&~completion_readout['ready'])
        p['matched']=p['matched']&completion_readout['ready']
        numerical=dict(numerical,ready=numerical['ready']&completion_readout['ready'],
                       needs_attention=numerical['needs_attention']|xp.any(bindings['live']&~completion_readout['ready']))
    marks=dict(query_complete=bindings['complete'],overflow=bindings['overflow'],candidate_lanes=bindings['candidate_lanes'],encoding=encoding,numerical=numerical)
    if capture:
        from device_match_capture import collect
        marks['capture']=collect(state,bindings,request,tokens,numerical,plan,xp,boundary_capture)
        if completion_readout is not None:marks['capture']['completion_readout']=completion_readout
    return p,marks


def step(state,plan,model,capacity,external_complete,eq_settled,xp,key_context=None,capture=False):
    p,marks=proposals(state,plan,model,capacity,external_complete,eq_settled,xp,capture)
    out,admission=commit(state,p,xp,key_context)
    if capture:marks['capture']=dict(marks['capture'],accepted=admission['accepted'])
    return out,dict(marks,admission=admission)


def run_round(state,blocks,model,stage,xp,capacity=16,external_complete=False,eq_settled=False,key_context=None,capture=False):
    if not blocks:raise ValueError('empty query catalog is not coverage')
    candidates=[];complete=xp.array(True);captures=[];boundary_cache={}
    max_atoms=max(len(plan['query']['atoms']) for _,plan in blocks)
    for stage_id,plan in blocks:
        p,marks=proposals(state,plan,model,capacity,external_complete,eq_settled,xp,capture,boundary_cache=boundary_cache)
        enabled=stage==stage_id
        p['matched']=p['matched']&enabled;p['missing_witness']=p['missing_witness']&enabled
        complete=complete&(~enabled|marks['query_complete'])
        for key in ('witness_sources','witness_generations','witness_valid'):
            value=p[key];pad=max_atoms-value.shape[1]
            p[key]=xp.concatenate([value,xp.full((capacity,pad),False if key=='witness_valid' else -1,value.dtype)],axis=1)
        candidates.append(p)
        if capture:captures.append(dict(marks['capture'],enabled=enabled))
    combined={k:xp.concatenate([p[k] for p in candidates],axis=0) for k in candidates[0]}
    out,marks=commit(state,combined,xp,key_context)
    marks['query_complete']=complete;marks['needs_attention']=marks['needs_attention']|~complete
    marks['new_tokens']=xp.sum(marks['accepted'].astype(xp.int32))
    marks['proposed_matches']=xp.sum(combined['matched'].astype(xp.int32))
    if capture:
        marks['captures']=tuple(dict(c,accepted=marks['accepted'][i*capacity:(i+1)*capacity]) for i,c in enumerate(captures))
    return out,marks
