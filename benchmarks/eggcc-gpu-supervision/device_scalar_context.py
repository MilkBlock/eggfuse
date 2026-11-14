"""Scalar-conditioned dense boundary messages, without scalar Eq authorization.

The selected family has at most one numeric scalar per template. A fixed Gaussian
of the actual scalar difference conditions neighbor messages on the consumer.
Integer IDs remain addresses; only actual numeric values enter floating work.
"""
import numpy as np
from device_boundary_context import compile_context,masks
from device_semantic_template import semantic


def compile_scalar_context(recipe,rid,width):
    base=compile_context(recipe,rid,width)
    slots=[];names=[]
    for raw in recipe['rules']:
        r,_=semantic(raw)
        scalar=[(i,s['sort']['name']) for i,s in enumerate(r['slots']) if s['sort']['kind']!='eq']
        if len(scalar)>1 or any(name not in ('i64','f64','f32','i32') for _,name in scalar):
            raise ValueError('scalar-context family requires at most one supported numeric scalar')
        slots.append(scalar[0][0] if scalar else -1);names.append(scalar[0][1] if scalar else None)
    return dict(base=base,scalar_slots=np.array(slots,np.int32),consumer_slot=slots[rid],
                compatible=np.array([name==names[rid] and name is not None for name in names],bool))


def encode(boundary,bindings,source_numbers,source_valid,consumer_numbers,consumer_valid,plan,xp):
    base=plan['base'];batch=len(bindings['live']);hidden=base['token_weight'].shape[1]
    if plan['consumer_slot']<0:
        return xp.zeros((batch,base['width']*hidden),xp.float32),xp.zeros((batch,len(base['ports'])),xp.float32)
    conn,_,safe,valid=masks(boundary,bindings,base,xp)
    eligible=boundary['live']&source_valid&plan['compatible'][safe]&xp.isfinite(source_numbers)
    good=bindings['live']&consumer_valid&xp.isfinite(consumer_numbers)
    delta=xp.where(good,consumer_numbers,0)[:,None]-xp.where(eligible,source_numbers,0)[None,:]
    weight=xp.exp(-.5*delta*delta)*eligible[None,:]*good[:,None]
    values=xp.where(eligible[:,None],boundary['tokens'],0)
    h=xp.tanh((values@base['token_weight'])[:,None,:]+base['roles'][safe]@base['role_weight'])
    h=xp.where((valid&eligible[:,None])[:,:,None],h,0).reshape(-1,hidden)
    weighted=conn.astype(xp.float32)*weight[:,None,:,None]
    count=xp.sum(weighted,axis=(-2,-1))
    result=weighted.reshape(batch,len(base['ports']),-1)@h
    result=xp.tanh(result/xp.sqrt(xp.maximum(count,1))[:,:,None])
    positions=(xp.arange(base['width'])[:,None]==base['ports'][None,:]).astype(xp.float32)
    return (positions[None,:,:]@result).reshape(batch,-1),count


def captured_numbers(capture,meta,plan):
    """Recover captured actual scalars; runtime already stores these numeric slots."""
    boundary=capture['boundary'];bindings=capture['bindings']
    source=np.zeros(len(boundary['rule']),np.float32);valid=np.zeros(len(source),bool)
    consumer=np.zeros(len(bindings['live']),np.float32);consumer_valid=np.zeros(len(consumer),bool)
    def number(identity,sort):
        value=meta['seed_scalars'].get(str(int(identity)))
        if value is None or value['sort']!=sort or isinstance(value.get('value'),bool) or not isinstance(value.get('value'),(int,float)):
            raise ValueError('numeric scalar identity not captured')
        return value['value']
    for row,rid in enumerate(boundary['rule']):
        if not boundary['live'][row] or not 0<=rid<len(plan['scalar_slots']):continue
        slot=plan['scalar_slots'][rid]
        if slot<0 or not boundary['slot_valid'][row,slot]:continue
        sort=meta['recipe']['rules'][rid]['slots'][slot]['sort']['name']
        source[row]=number(boundary['slots'][row,slot],sort);valid[row]=True
    slot=plan['consumer_slot'];rid=int(capture['rule'])
    if slot>=0:
        for lane in np.flatnonzero(bindings['live']&bindings['slot_valid'][:,slot]):
            consumer[lane]=number(bindings['slots'][lane,slot],meta['recipe']['rules'][rid]['slots'][slot]['sort']['name']);consumer_valid[lane]=True
    return source,valid,consumer,consumer_valid
