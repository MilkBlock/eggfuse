"""Enumerate all typed equality partitions of bounded query interfaces.

Complete for the listed slot-only constructor query's port equality patterns,
after constructor congruence; not complete for scalar values, hidden facts,
mutable reads, generated-token states, or arbitrary multi-Cell interactions.
"""
import itertools
import math
from collections import OrderedDict
import numpy as np
import mlx.core as mx
from device_snapshot_import import identity
from reference_union_family import Reference
from neural_snapshot_candidates import import_interfaces,binding_key,relational_edges
from neural_ordered_relations import demand,incidence
from multi_entry_ridge import template


def partitions(n):
    """Restricted-growth strings: each set partition exactly once."""
    if n==0:
        yield ();return
    def extend(prefix,maximum):
        if len(prefix)==n:
            yield tuple(prefix);return
        for value in range(maximum+2):
            yield from extend(prefix+[value],max(maximum,value))
    yield from extend([0],0)


def typed_snapshots(recipe,rule,scalar_base,pattern_limit=200000):
    groups=OrderedDict()
    for ai,atom in enumerate(rule['query']):
        for fi,arg in enumerate(atom['args']):
            if 'slot' not in arg:raise ValueError('slot-only query required')
            sort=rule['slots'][arg['slot']]['sort']
            groups.setdefault((sort['kind'],sort['name']),[]).append((ai,fi))
    largest=max(map(len,groups.values()),default=0)
    bell=[1]
    for n in range(largest):bell.append(sum(math.comb(n,k)*bell[k] for k in range(n+1)))
    if math.prod(bell[len(p)] for p in groups.values())>pattern_limit:
        raise ValueError('typed pattern capacity exceeded; coverage is unresolved')
    options=[list(partitions(len(positions))) for positions in groups.values()]
    for assignment in itertools.product(*options):
        fields=[[None]*len(atom['args']) for atom in rule['query']]
        for ((kind,name),positions),pattern in zip(groups.items(),assignment):
            for (ai,fi),block in zip(positions,pattern):
                if kind=='eq':value=dict(sort=name,eq=str(block))
                elif kind=='i64':value=dict(sort=name,value=scalar_base+block)
                elif kind=='String':value=dict(sort=name,value=f's{scalar_base}:{block}')
                else:raise ValueError('unsupported scalar '+kind)
                fields[ai][fi]=value
        ids={}
        for row in fields:
            for value in row:ids.setdefault(identity(value),len(ids))
        ref=Reference(recipe,[],ids)
        for atom,row in zip(rule['query'],fields):
            vs=[ids[identity(v)] for v in row];ref.construct(atom['call']['table'],vs[:-1],vs[-1])
        ref.close()
        rows=[]
        for atom,row in zip(rule['query'],fields):
            values=[dict(v,eq=str(ref.root(ids[identity(v)]))) if 'eq' in v else v for v in row]
            rows.append(dict(table=atom['call']['table'],values=values,subsumed=False))
        yield dict(rows=rows)


def typed_candidates(recipe,scalar_bases=(0,3),ordered=True):
    atoms=max(len(r['query']) for r in recipe['rules'])
    result={k:[] for k in ('x','edges','mask','request','valid','rule')}
    if ordered:result['relations']=[]
    coverage=[]
    for rid,rule in enumerate(recipe['rules']):
        seen=set();enumerated=positive=0
        for scalar_base in scalar_bases:
            for snapshot in typed_snapshots(recipe,rule,scalar_base):
                enumerated+=1
                rows,ids,_,x,labels,roles=import_interfaces(recipe,snapshot)
                address={(row['table'],tuple(identity(v) for v in row['values'])):i for i,row in enumerate(rows)}
                selected=[address[(row['table'],tuple(identity(v) for v in row['values']))] for row in snapshot['rows']]
                indices=np.array([selected+[0]*(atoms-len(selected))],np.int32)
                mask=np.array([[True]*len(selected)+[False]*(atoms-len(selected))])
                actual=labels[indices].copy();actual[~mask]=-1
                relation=incidence(actual,demand(rule,atoms,labels.shape[1]))[0]
                edge=np.array(relational_edges(mx.array(labels),mx.array(roles),mx.array(indices)))[0]
                _,request=template(rule)
                value=binding_key(rule,selected,rows,ids) is not None
                features=x[indices][0]
                fingerprint=b''.join(v.tobytes() for v in (features,edge,mask[0],request,relation))
                if fingerprint in seen:continue
                seen.add(fingerprint);positive+=value
                for k,v in dict(x=features,edges=edge,mask=mask[0],request=request,valid=value,rule=rid).items():result[k].append(v)
                if ordered:result['relations'].append(relation)
        coverage.append(dict(rule=rid,complete_typed_partition_enumeration=True,enumerated_patterns_with_scalar_variants=enumerated,distinct_features=len(seen),positive=positive,negative=len(seen)-positive))
    data={k:np.array(v) for k,v in result.items()};data['valid']=data['valid'].astype(np.float32)
    return data,coverage
