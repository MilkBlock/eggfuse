"""Experimental whole-state token readout on the resident GPU path.

Only floating tokens change. Exact slots, matching, effects, ownership and
termination remain authoritative. No label, host feedback or new union occurs.
"""
import numpy as np
from device_semantic_template import semantic
from device_completion_states import compile_states, compile_tokens, project, tokens
from token_eq_readout import pair_layout, quotient_layout, static_equalities, features
from multi_entry_ridge import vec


def compile_readout(rule, decoder_w, decoder_coef):
    rule,_=semantic(rule)
    plan=compile_states(rule);tp=compile_tokens(rule,plan)
    if any(rule['slots'][s]['definition']!='query' for s in tp['scalar_slots']):
        raise ValueError('completion token requires executed scalar result; unsupported template')
    pairs,q,_,_,_=pair_layout(rule);quotient=quotient_layout(rule,pairs,static_equalities(rule,pairs))
    if not len(plan['states'][0]):raise ValueError('completion readout needs a dynamic Eq query')
    edges=[];mapping=[]
    for (a,b),out in zip(pairs,quotient['expansion']):
        if out>=0 and all(rule['slots'][s]['definition']=='query' for s in (a,b)):
            edges.append((a,b));mapping.append(out)
    incidence=np.zeros((len(edges),plan['states'].shape[1]),np.float32)
    for i,j in enumerate(mapping):incidence[i,j]=1
    scalar_slots=tp['scalar_slots']
    return dict(states=plan['states'],token=tp,q=q,s=quotient['s'],d=quotient['d'],p=quotient['p'],
        w=decoder_w,coef=decoder_coef,edges=np.array(edges,np.int32).reshape(-1,2),incidence=incidence,
        scalar_slots=scalar_slots,numeric_roles=np.array([vec(('numeric',rule['slots'][s]['sort']['name'])) for s in scalar_slots],np.float32).reshape(-1,64))


def scalar_inputs(proposal,plan,xp):
    slots=plan['scalar_slots'];batch=len(proposal['tokens'])
    if not len(slots):return xp.zeros((batch,0,64),xp.float32),xp.ones(batch,xp.bool_)
    number=proposal['scalar_numbers'][:,slots];numeric=proposal['scalar_numeric'][:,slots]
    finite=xp.isfinite(number);safe=xp.where(finite,number,0)
    codes=xp.tanh((xp.sign(safe)*xp.log1p(xp.abs(safe)))[:,:,None]*plan['numeric_roles'])
    codes=xp.where(numeric[:,:,None],codes,proposal['scalar_codes'][:,slots])
    valid=proposal['slot_valid'][:,slots]&xp.where(numeric,finite,proposal['scalar_valid'][:,slots])
    return codes,xp.all(valid,axis=1)&xp.all(xp.isfinite(codes),axis=(1,2))


def apply(raw,bindings,codes,scalar_ready,plan,xp):
    batch=len(raw);count=plan['states'].shape[1]
    z=xp.broadcast_to(raw[:,None,:],(batch,count,128)).reshape(-1,128)
    tiled=lambda a:xp.broadcast_to(a,(batch,count,64)).reshape(-1,64)
    x=features(z,tiled(plan['q']),tiled(plan['s']),tiled(plan['d']),tiled(plan['p']),plan['w'],xp)
    scores=(x@plan['coef']).reshape(batch,count)
    edges=plan['edges'];left=edges[:,0];right=edges[:,1]
    roots=bindings['slot_roots'];valid=bindings['slot_valid']
    evidence=valid[:,left]&valid[:,right]&(roots[:,left]>=0)&(roots[:,right]>=0)&(roots[:,left]==roots[:,right])
    required=(evidence.astype(xp.float32)@plan['incidence'])>0
    finite=xp.all(xp.isfinite(scores),axis=1)&xp.all(xp.isfinite(raw),axis=1)
    selected,chosen=project(xp.where(finite[:,None],scores,0),plan['states'],required,xp)
    output=tokens(chosen,xp.where(scalar_ready[:,None,None],codes,0),plan['token'],xp)
    ready=finite&scalar_ready&xp.all(xp.isfinite(output),axis=1)
    return output,dict(ready=ready,chosen=chosen,scores=scores,required=required,
        selected=selected,raw_tokens=raw,scalar_codes=codes,scalar_ready=scalar_ready)
