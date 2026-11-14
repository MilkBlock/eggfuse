"""Bake a sealed semantic owner spanning producer and consumer Cell templates.

A descriptor of completed facts, not an executable query or permission to reorder
Runs. Original programs remain authoritative; this layout is their token target.
"""
from copy import deepcopy
import hashlib
import json
from neural_semantic_owner import _sealed


def compose(recipe,plan):
    if not plan['covered']:raise ValueError('combined payload not covered')
    source,target=[recipe['rules'][plan[k]] for k in ('producer','consumer')]
    if source.get('token_layout') or target.get('token_layout'):
        raise ValueError('compose original semantic templates before instruction lowering')
    proofs=[_sealed(r) for r in (source,target)]
    if any(p is None for p in proofs):raise ValueError('unsupported sealed semantics')
    tables={t['name']:t['kind'] for t in recipe['tables']}
    if any(tables.get(t)!='constructor' for p in proofs for t,_ in p[0]):
        raise ValueError('mutable fact requires an explicit boundary')
    smap=[int(i) for i in plan['projection'][:len(source['slots'])]]
    tmap=list(range(len(target['slots'])))
    slots=deepcopy(target['slots']);size=max(len(slots),max(smap,default=-1)+1)
    slots.extend([None]*(size-len(slots)))
    for i,j in enumerate(smap):
        if slots[j] is None:slots[j]=deepcopy(source['slots'][i])
        elif slots[j]['sort']!=source['slots'][i]['sort']:raise ValueError('mapped sort mismatch')
    if any(s is None for s in slots):raise ValueError('noncompact combined layout')
    facts=set();equal=set()
    for (rows,pairs),mapping in zip(proofs,(smap,tmap)):
        facts.update((name,tuple(mapping[i] for i in args)) for name,args in rows)
        for pair in pairs:
            if len(pair)!=2:raise ValueError('binary equality required')
            a,b=sorted(mapping[i] for i in pair)
            if a!=b:equal.add((a,b))
    # All these facts have already been established. Never schedule this
    # descriptive query as a replacement for original stage/effect execution.
    for slot in slots:slot['definition']='query'
    descriptor=dict(slots=slots,
        query=[dict(call=dict(table=name),args=[dict(slot=i) for i in args]) for name,args in sorted(facts)],
        effects=[dict(kind='union',args=[dict(slot=a),dict(slot=b)]) for a,b in sorted(equal)])
    fingerprint=hashlib.sha256(json.dumps(descriptor,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return dict(rule=descriptor,source_projection=smap,target_projection=tmap,
                identity=fingerprint,source_rule=plan['producer'],target_rule=plan['consumer'])


def values(layout,source_values,target_values,ref):
    """Oracle labels only; never used to construct runtime token inputs."""
    out=[None]*len(layout['rule']['slots'])
    for incoming,mapping in ((target_values,layout['target_projection']),(source_values,layout['source_projection'])):
        for value,dst in zip(incoming,mapping):
            value=ref.root(value)
            if out[dst] is not None and out[dst]!=value:raise ValueError('binding violates compiled projection')
            out[dst]=value
    if any(v is None for v in out):raise ValueError('incomplete combined label')
    return out


def request(layout):
    """Ordered static layout evidence for a slot-indexed semantic readout.

The ordinary request pools roles and is invariant under port permutation. That
cannot identify output pair columns when the source-to-owner projection changes.
Only template port positions and wiring enter here, never instance identities.
"""
    import numpy as np
    from multi_entry_ridge import template,vec
    roles,_=template(layout['rule'])
    parts=[np.tanh(role+vec(('owner-port',i))) for i,role in enumerate(roles)]
    for side in ('source','target'):
        parts.extend(vec(('owner-projection',side,i,j)) for i,j in enumerate(layout[side+'_projection']))
    return np.tanh(np.sum(parts,axis=0)/np.sqrt(len(parts))).astype(np.float32)
