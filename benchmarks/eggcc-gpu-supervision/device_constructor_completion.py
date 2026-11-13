"""Bounded constructor completion and token refresh between Entry rounds.

Unsupported effects stay pending at their original effect_pc. External witness
coverage and a settled Eq snapshot are caller obligations, not inferred here.
"""
import numpy as np
from compile_constructor_sites import compile_sites
from device_witness_views import compile_view,project
from device_constructor_results import execute_site
from device_input_features import compile_inputs
from device_token_refresh import refresh


def compile_completion(recipe,width):
    compiled=compile_sites(recipe);sites=compiled['sites']
    views={(s['table'],len(s['args'])):compile_view(recipe,s['table'],len(s['args'])) for s in sites}
    layouts=[]
    for rid in sorted({s['rule'] for s in sites}):
        rule=recipe['rules'][rid];n=len(rule['slots'])
        if n>width:raise ValueError('completion slot width too small')
        base=compile_inputs(rule)
        layout=dict(required=np.zeros((1,width),bool),eq=np.zeros((1,width),bool),sorts=np.full((1,width),-1,np.int32),
                    roles=np.zeros((1,width,64),np.float32),numeric_roles=np.zeros((1,width,64),np.float32))
        layout['required'][:,:n]=True
        for key in ('eq','sorts','numeric_roles'):layout[key][:,:n]=base[key]
        layout['roles'][:,:n]=base['roles'][:,:,:64]
        layouts.append((rid,layout))
    return dict(sites=sites,views=views,layouts=layouts,marks=compiled['marks'])


def complete(state,plan,next_id,limit,quota,external_complete,eq_settled,xp):
    attention=xp.array(False);executed=xp.array(0,dtype=xp.int32)
    for site in plan['sites']:
        view=project(state,plan['views'][(site['table'],len(site['args']))],external_complete,eq_settled,xp)
        state,outcome=execute_site(state,site,view,next_id,limit,quota,xp)
        next_id=outcome['next_id'];attention=attention|outcome['needs_attention']
        executed=executed+xp.sum(outcome['ready'].astype(xp.int32))
    refreshed=xp.array(0,dtype=xp.int32)
    rows,width=state['slots'].shape
    for rid,layout in plan['layouts']:
        selected=dict(state,present=state['present']&(state['keys'][:,0]==rid))
        codes=state.get('scalar_codes',xp.zeros((rows,width,64),xp.float32))
        valid=state.get('scalar_valid',xp.zeros((rows,width),xp.bool_))
        if 'scalar_numbers' in state and 'scalar_numeric' in state:
            number=state['scalar_numbers'];finite=xp.isfinite(number);safe=xp.where(finite,number,0)
            numeric=xp.tanh((xp.sign(safe)*xp.log1p(xp.abs(safe)))[:,:,None]*layout['numeric_roles'])
            codes=xp.where(state['scalar_numeric'][:,:,None],numeric,codes)
            valid=xp.where(state['scalar_numeric'],finite,valid)
        updated,marks=refresh(selected,layout['sorts'],layout['eq'],layout['required'],layout['roles'],codes,valid,eq_settled,xp)
        updated['present']=state['present'];state=updated
        refreshed=refreshed+xp.sum(marks['refreshed'].astype(xp.int32))
        attention=attention|marks['needs_attention']
    pending=state['present']&state['active']&(~state['settled']|state.get('token_dirty',xp.zeros_like(state['present'])))
    return state,next_id,dict(executed=executed,refreshed=refreshed,needs_attention=attention|xp.any(pending),pending=pending)
