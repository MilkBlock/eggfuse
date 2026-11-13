"""Ephemeral Eq-aware comparison views over stable input identities.

No canonical key is retained or repaired. Scalar keys remain exact caller-owned
encodings; this module does not turn numeric floats into identities.
"""
import numpy as np


def compile_types(recipe):
    names=sorted({s['sort']['name'] for r in recipe['rules'] for s in r['slots'] if s['sort']['kind']=='eq'})
    inputs=[[s for s in r['slots'] if s['definition']=='query'] for r in recipe['rules']]
    width=max(map(len,inputs),default=0);types=np.full((len(inputs),width),-2,np.int32)
    for rid,slots in enumerate(inputs):
        for i,s in enumerate(slots):types[rid,i]=names.index(s['sort']['name']) if s['sort']['kind']=='eq' else -1
    return types,names


def comparison_view(keys,context,xp):
    types=xp.array(context['types']);roots=context['roots'];sorts=context['sorts']
    if keys.shape[1]!=types.shape[1]+1 or roots.shape!=sorts.shape or roots.shape[0]<1:raise ValueError('typed key layout mismatch')
    rule=keys[:,0];valid_rule=(rule>=0)&(rule<types.shape[0]);kind=types[xp.clip(rule,0,types.shape[0]-1)]
    values=keys[:,1:];eq=kind>=0;safe=xp.clip(values,0,roots.shape[0]-1);root=roots[safe]
    root_safe=xp.clip(root,0,roots.shape[0]-1)
    valid_eq=(values>=0)&(values<roots.shape[0])&(root>=0)&(root<roots.shape[0])&(sorts[safe]==kind)&(sorts[root_safe]==kind)&(roots[root_safe]==root)
    valid=valid_rule&xp.all((~eq|valid_eq)&((kind!=-2)|(values==-1)),axis=1)
    view=xp.concatenate([keys[:,:1],xp.where(eq,root,values)],axis=1)
    return view,valid
