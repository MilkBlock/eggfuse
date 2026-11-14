"""Live-source ridge inference. No observed future schedule or output labels.

Requests must be compiled/dynamically matched by the caller. This module checks
source lifetimes and evaluates the existing trained feature map, not matching,
ownership coverage, scalar computation or a completion proof.
"""
from device_token_commit import closed_entry_proposals


def encode_features(state, request, model, xp, layout=None):
    sources=request['sources']
    mask=request['edge_valid']
    capacity=state['tokens'].shape[0]
    safe=xp.clip(sources,0,capacity-1)
    live=((sources>=0)&(sources<capacity)&state['present'][safe]&state['visible'][safe]
          &state['settled'][safe]&(state['generation'][safe]==request['generations'])
          &~state.get('token_dirty',xp.zeros_like(state['present']))[safe])
    # Shared readers remain useful after activation ownership moves elsewhere.
    values=state['tokens'][safe]
    finite_source=xp.all(xp.isfinite(values),axis=2)
    usable=mask&live&finite_source
    values=xp.where(usable[:,:,None],values,0)
    coefficients=request if layout is None else layout
    layout_ready=xp.ones(sources.shape[0],dtype=xp.bool_)
    edge=coefficients['edge'];route=coefficients['route']
    if 'layout_index' in request:
        index=request['layout_index']
        layout_ready=(index>=0)&(index<edge.shape[0])
        index=xp.clip(index,0,edge.shape[0]-1)
        edge=edge[index];route=route[index]
    edge=xp.where(mask[:,:,None],edge,0)
    route=xp.where(mask[:,:,None],route,0)
    count=xp.maximum(xp.sum(mask.astype(xp.float32),axis=1),1)
    pool=(xp.swapaxes(route,1,2)@(values*edge))/xp.sqrt(count[:,None,None])
    pool=pool.reshape(sources.shape[0],-1)
    seed=request['seed'];q=request['q']
    if 'source_relation' in coefficients:
        from device_source_relations import encode as encode_relations
        relation=coefficients['source_relation']
        if 'layout_index' in request:relation=relation[index]
        relation=xp.broadcast_to(relation,(*sources.shape,relation.shape[-1]))
        q=xp.concatenate([q,encode_relations(sources,relation,usable,xp)],axis=1)
    missing_owner=xp.zeros(sources.shape[0],dtype=xp.bool_)
    if 'owner_relation' in coefficients:
        from device_owner_relations import context as owner_context
        owner_role=coefficients['owner_relation']
        if 'layout_index' in request:owner_role=owner_role[index]
        owner_role=xp.broadcast_to(owner_role,(*sources.shape,owner_role.shape[-1]))
        owner_features,missing_owner=owner_context(state,sources,mask,owner_role,xp)
        q=xp.concatenate([q,owner_features],axis=1)
    repeated=xp.concatenate([seed]*coefficients['route'].shape[2],axis=1)
    raw=xp.concatenate([seed,q,pool,repeated*pool],axis=1)
    features=xp.concatenate([xp.ones((seed.shape[0],1),dtype=xp.float32),raw,xp.tanh(raw@model['w'])],axis=1)
    if 'boundary_features' in request:
        features=xp.concatenate([features,request['boundary_features']],axis=1)
    missing=xp.any(mask&~live,axis=1)
    nonfinite=xp.any(mask&~finite_source,axis=1)|~xp.all(xp.isfinite(features),axis=1)
    ready=request['input_ready']&layout_ready&~missing&~missing_owner&~nonfinite
    return features,dict(ready=ready,missing_source=missing,missing_owner=missing_owner,nonfinite=nonfinite,
                       missing_layout=~layout_ready,missing_input=~request['input_ready'],needs_attention=xp.any(~ready))


def infer(state, request, model, xp, layout=None):
    features,marks=encode_features(state,request,model,xp,layout)
    if features.shape[1]!=model['coef'].shape[0]:raise ValueError('ridge feature/model width mismatch')
    tokens=xp.tanh(features@model['coef'])
    nonfinite=marks['nonfinite']|~xp.all(xp.isfinite(tokens),axis=1)
    ready=marks['ready']&~nonfinite
    return tokens,dict(marks,ready=ready,nonfinite=nonfinite,needs_attention=xp.any(~ready))


def proposals(state,plan,stage,request,model,xp,layout=None):
    """Requests align with source-major, entry-minor compiled candidates.

    Replace the old square test transform, rather than evaluating both paths.
    Numerical readiness cannot grant query or effect/ownership coverage.
    """
    tokens,marks=infer(state,request,model,xp,layout)
    p=closed_entry_proposals(state,plan,stage,xp,token_values=tokens)
    wanted=p['matched']
    p['matched']=wanted&marks['ready']
    p['missing_witness']=p['missing_witness']|(wanted&~marks['ready'])
    return p,marks
