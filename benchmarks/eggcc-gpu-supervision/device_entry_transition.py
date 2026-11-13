"""Single-source compiled Entry -> live input features -> ridge -> admission.

No saved successful bindings are consumed. Existing catalog coverage remains the
limit: this does not implement multi-source joins or prove stage saturation.
"""
import numpy as np
from multi_entry_ridge import template
from device_input_features import compile_inputs,encode_inputs
from device_ridge_transition import infer
from device_token_commit import closed_entry_proposals,commit


def compile_features(recipe,entry,channels=4):
    if not 1<=channels<=8:raise ValueError('unsupported channel count')
    source=recipe['rules'][entry['producer']];consumer=recipe['rules'][entry['consumer']]
    inputs=[i for i,s in enumerate(consumer['slots']) if s['definition']=='query']
    pr,_=template(source);cr,_=template(consumer)
    routing=np.random.default_rng(777).normal(0,1/np.sqrt(128),(128,channels-1)).astype(np.float32)
    edges=[];routes=[]
    for slot,origin in zip(inputs,entry['projection']):
        if consumer['slots'][slot]['sort']['kind']!='eq':continue
        edges.append(np.concatenate([np.tanh(cr[slot]+pr[origin]),np.tanh(cr[slot]-pr[origin])]))
        routes.append(np.concatenate([np.ones(1,np.float32),np.tanh(3*np.concatenate([cr[slot],pr[origin]])@routing)]))
    count=len(edges)
    return compile_inputs(consumer),dict(edge=np.array([edges or [np.zeros(128)]],np.float32),
        route=np.array([routes or [np.zeros(channels)]],np.float32),edge_valid=np.array([[True]*count or [False]]))


def step(state,plan,input_layout,coefficient_layout,model,stage,xp):
    if plan['producer'].shape[0]!=1 or 'destination_projection' not in plan:
        raise ValueError('one source-slot Entry required per compiled block')
    n=state['tokens'].shape[0];width=input_layout['required'].shape[1]
    # Match and project once. No square test map or host-produced feature vector.
    p=closed_entry_proposals(state,plan,stage,xp,token_values=xp.zeros_like(state['tokens']))
    roots=p.get('slot_roots',p['slots'])[:,:width]
    inputs=dict(roots=roots,valid=p['slot_valid'][:,:width],numbers=xp.zeros((n,width),xp.float32),numeric=xp.zeros((n,width),xp.bool_),
                scalar_codes=xp.zeros((n,width,64),xp.float32),scalar_valid=xp.zeros((n,width),xp.bool_))
    # Source columns use the same slot addresses as exact values; there is no
    # independent binding lookup. These are optional for Eq-only templates.
    origin=plan['projection'][0][plan['destination_projection'][0]]
    projected=plan['destination_valid'][0]
    for column,key in [('scalar_numbers','numbers'),('scalar_numeric','numeric'),('scalar_codes','scalar_codes'),('scalar_valid','scalar_valid')]:
        if column in state:
            value=state[column][:,origin]
            mask=projected[None,:] if value.ndim==2 else projected[None,:,None]
            value=xp.where(mask,value,0)
            inputs[key]=value[:,:width]
            p[column]=value
    features,encoding=encode_inputs(inputs,input_layout,xp)
    e=coefficient_layout['edge'].shape[1]
    request=dict(features,sources=xp.broadcast_to(xp.arange(n)[:,None],(n,e)),
        generations=xp.broadcast_to(state['generation'][:,None],(n,e)),
        edge_valid=xp.broadcast_to(coefficient_layout['edge_valid'],(n,e)))
    tokens,numeric=infer(state,request,model,xp,coefficient_layout)
    wanted=p['matched'];p['tokens']=tokens;p['matched']=wanted&numeric['ready']
    p['missing_witness']=p['missing_witness']|(wanted&~numeric['ready'])
    out,admission=commit(state,p,xp)
    return out,dict(admission=admission,encoding=encoding,numeric=numeric)
