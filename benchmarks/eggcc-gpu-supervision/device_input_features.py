"""Compile shared input roles and encode live Cell slots on device.

Equality identity stays integer. Numeric scalar features use f32 arithmetic;
exact semantic scalar storage and operations remain outside this encoder.
"""
import numpy as np
from multi_entry_ridge import vec
from device_semantic_template import template,neighborhood_template
from device_token_refresh import encode_batch


def compile_inputs(rule):
    roles,q=template(rule);near,nq=neighborhood_template(rule)
    sorts=sorted({s['sort']['name'] for s in rule['slots'] if s['sort']['kind']=='eq'})
    return dict(roles=np.concatenate([roles,near],axis=1)[None],q=q[None],nq=nq[None],
        required=np.array([[s['definition']=='query' for s in rule['slots']]]),
        eq=np.array([[s['sort']['kind']=='eq' for s in rule['slots']]]),
        sorts=np.array([[sorts.index(s['sort']['name']) if s['sort']['kind']=='eq' else -1 for s in rule['slots']]],np.int32),
        numeric_roles=np.array([[vec(('numeric',s['sort']['name'])) for s in rule['slots']]],np.float32))


def encode_inputs(inputs,layout,xp):
    """Inputs are current projected slots, never completed output labels.

    numeric marks values with a supported f32 numeric representation. Other
    scalars need an available resident code. Required/unavailable inputs block
    readiness; an empty padding slot cannot become evidence of a query match.
    """
    required=layout['required'];eq=layout['eq'];numeric=inputs['numeric']
    number=inputs['numbers'];finite=xp.isfinite(number)
    safe=xp.where(finite,number,0)
    magnitude=xp.sign(safe)*xp.log1p(xp.abs(safe))
    code=xp.tanh(magnitude[:,:,None]*layout['numeric_roles'])
    code=xp.where(numeric[:,:,None],code,inputs['scalar_codes'])
    scalar_ready=xp.where(numeric,finite,inputs['scalar_valid'])&xp.all(xp.isfinite(code),axis=2)
    missing=xp.any(required&(~inputs['valid']|(~eq&~scalar_ready)),axis=1)
    invalid_eq=xp.any(required&eq&((inputs['roots']<0)|(layout['sorts']<0)),axis=1)
    both=encode_batch(inputs['roots'],layout['sorts'],eq,required&inputs['valid'],layout['roles'],xp.concatenate([code,code],axis=2),xp)
    # Both role systems share one partition mask and one dense aggregation.
    seed=xp.concatenate([both[:,:64],both[:,128:192]],axis=1)
    neighborhood=xp.concatenate([both[:,64:128],both[:,192:256]],axis=1)
    n=seed.shape[0]
    q=xp.concatenate([xp.broadcast_to(layout['q'],(n,64)),neighborhood,xp.broadcast_to(layout['nq'],(n,64))],axis=1)
    ready=~missing&~invalid_eq&xp.all(xp.isfinite(seed),axis=1)&xp.all(xp.isfinite(q),axis=1)
    return dict(seed=seed,q=q,input_ready=ready),dict(missing_input=missing,invalid_eq=invalid_eq,needs_attention=xp.any(~ready))


def infer_from_slots(state,request,model,inputs,input_layout,xp,coefficient_layout=None):
    from device_ridge_transition import infer
    features,encoding_marks=encode_inputs(inputs,input_layout,xp)
    dynamic=dict(request)
    dynamic.update(features)
    if 'input_ready' in request:dynamic['input_ready']=features['input_ready']&request['input_ready']
    tokens,marks=infer(state,dynamic,model,xp,coefficient_layout)
    return tokens,marks,encoding_marks
