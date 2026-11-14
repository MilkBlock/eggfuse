"""Compile positive Eq consequences of sealed Cell definitions and ownership.

Proofs are conditional on successful matching/completion of the given Cell.
Unknown pairs are never declared unequal. No instance IDs or oracle labels enter
this compiler. Congruence saturation happens here, not in the device readout.
"""
import numpy as np
from neural_semantic_owner import _sealed


def partition(recipe,rule,assumptions=()):
    facts=_sealed(rule)
    if facts is None:raise ValueError('unsupported sealed operations')
    tables={t['name']:t['kind'] for t in recipe['tables']}
    if any(tables.get(name)!='constructor' for name,_ in facts[0]):raise ValueError('mutable fact')
    slots=rule['slots'];parents=list(range(len(slots)))
    def root(i):
        while parents[i]!=i:i=parents[i]
        return i
    def merge(a,b):
        if slots[a]['sort']!=slots[b]['sort']:raise ValueError('ill-typed equality')
        a,b=root(a),root(b)
        if a==b:return False
        parents[max(a,b)]=min(a,b);return True
    for pair in list(facts[1])+list(assumptions):
        if len(pair)!=2:raise ValueError('binary equality required')
        merge(*pair)
    changed=True
    while changed:
        changed=False;keys={}
        for name,args in sorted(facts[0]):
            if not args:raise ValueError('missing constructor result')
            key=(name,tuple(root(i) for i in args[:-1]))
            if key in keys:changed=merge(keys[key],args[-1]) or changed
            else:keys[key]=args[-1]
    return np.array([root(i) for i in range(len(slots))],np.int32)


def compile_rule(recipe,rule,width):
    n=len(rule['slots']);a,b=np.triu_indices(width,1)
    if n>width:raise ValueError('Eq layout capacity')
    known=np.zeros(len(a),bool)
    try:roots=partition(recipe,rule)
    except ValueError as e:return dict(known=known,supported=False,reason=str(e))
    for k,(i,j) in enumerate(zip(a,b)):
        if j<n and rule['slots'][i]['sort']['kind']=='eq' and rule['slots'][i]['sort']==rule['slots'][j]['sort']:
            known[k]=roots[i]==roots[j]
    return dict(known=known,supported=True,reason='sealed positive consequences')


def compile_owner(recipe,plan,width):
    from neural_combined_cell import compose
    layout=compose(recipe,plan);rule=layout['rule'];roots=partition(recipe,rule)
    source,target=layout['source_projection'],layout['target_projection']
    def equal(i,j):return rule['slots'][i]['sort']['kind']=='eq' and rule['slots'][i]['sort']==rule['slots'][j]['sort'] and roots[i]==roots[j]
    a,b=np.triu_indices(width,1);out={}
    for name,ports in (('source',source),('target',target)):
        out[name+'_known_eq']=np.array([j<len(ports) and equal(ports[i],ports[j]) for i,j in zip(a,b)],bool)
    out['cross_known_eq']=np.array([i<len(source) and j<len(target) and equal(source[i],target[j]) for i in range(width) for j in range(width)],bool)
    return out


def apply(scores,known,xp):
    # A nonfinite proposal is still a failure, even on a proven pair.
    return xp.where(known&xp.isfinite(scores),xp.ones_like(scores),scores)
