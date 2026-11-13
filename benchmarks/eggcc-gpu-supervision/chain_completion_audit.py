"""Finite Bake candidate decoding of two-step Cell predictions.

The candidate dictionary includes held-out symbolic states; this is selection
within a known catalog, not proof of live correctness or novel-state discovery.
"""
import numpy as np
import mlx.core as mx
from dominator_completion import compose,freeze
from cell_token_successors import match_consumer
from decode_cell_completion import representation,retention


def candidates(source,rules,tables,expected,ports,prior_map,encode_state,capacity):
    entries=[];index={};unsupported=0;exhausted=0
    def add(completion):
        if not retention(source,completion['facts'],completion['source_map']):raise ValueError('candidate loses first completion')
        key=repr(representation(completion['facts'],completion['source_map']))
        if key not in index:
            quotient={freeze(a):freeze(b) for a,b in completion['source_map']}
            mapping=[(port,quotient[freeze(value)]) for port,value in prior_map]
            index[key]=len(entries)
            entries.append(encode_state(completion['facts'],ports,capacity,mapping))
        return index[key]
    symbols=sorted({freeze(v) for _,args,*_ in source for v in args},key=repr)
    add(dict(facts=source,source_map=[(v,v) for v in symbols]))
    for rule in rules:
        matches,full=match_consumer(rule,source,limit=32)
        if full:exhausted+=1;continue
        for match in matches:
            completion,reason=compose(source,rule,match['inputs'],tables)
            if reason:unsupported+=1;continue
            add(completion)
    key=repr(representation(expected['facts'],expected['source_map']))
    if key not in index:raise ValueError('expected completion absent from candidate enumeration')
    return np.array(entries,np.float32),index[key],dict(unsupported_matches=unsupported,exhausted_rule_enumerations=exhausted)


def pack(catalogs,body_width):
    """Scale body and live boundary groups equally, excluding padded channels."""
    width=catalogs[0][0].shape[1];count=max(len(c[0]) for c in catalogs)
    prototypes=np.zeros((len(catalogs),count,width),np.float32)
    valid=np.zeros((len(catalogs),count),bool);scale=np.zeros((len(catalogs),width),np.float32)
    for i,(values,expected,live_width) in enumerate(catalogs):
        prototypes[i,:len(values)]=values;valid[i,:len(values)]=True
        scale[i,:body_width]=1/np.sqrt(body_width)
        scale[i,body_width:body_width+live_width]=1/np.sqrt(max(1,live_width))
    return prototypes,valid,scale


def decode(values,prototypes,valid,scale):
    # Dense floating batched distances, no per-candidate lookup or host branch.
    delta=(values[:,None,:]-prototypes)*scale[:,None,:]
    distance=mx.where(valid,mx.sum(delta*delta,axis=2),mx.inf)
    selected=mx.argmin(distance,axis=1)
    best=mx.take_along_axis(distance,selected[:,None],axis=1)[:,0]
    alternatives=mx.where(mx.arange(prototypes.shape[1])[None,:]==selected[:,None],mx.inf,distance)
    return selected,mx.min(alternatives,axis=1)-best


def audit(values,selected,emitted,prototypes,valid,scale,expected):
    totals=dict(cases=len(values),emitted=int(np.sum(emitted)),exact_target=0,wrong_target=0,ambiguous=0,not_emitted=int(np.sum(~emitted)))
    for v,choice,active,ps,allowed,w,want in zip(values,selected,emitted,prototypes,valid,scale,expected):
        d=np.sum(((ps.astype(np.float64)-v.astype(np.float64))*w.astype(np.float64))**2,axis=1)
        d[~allowed]=np.inf;best=d.min();ties=np.flatnonzero(d<=best+1e-7)
        if d[choice]>best+1e-5:raise ValueError('device candidate selection fails f64 distance check')
        if not active:continue
        if len(ties)>1 or int(choice) not in ties:totals['ambiguous']+=1
        elif int(choice)==want:totals['exact_target']+=1
        else:totals['wrong_target']+=1
    return totals
