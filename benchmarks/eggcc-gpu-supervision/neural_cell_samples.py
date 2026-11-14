"""Synthetic candidate tuples for an entire constructor Cell family.

Candidate validity and immediate-effect targets come from exact local semantics.
No real Run inputs are sampled. This does not enumerate runtime candidates.
"""
import json
import numpy as np
from synthetic_cell_inputs import canonical_seed
from device_snapshot_import import identity
from multi_entry_ridge import template,scalar,encode
from reference_union_family import Reference
from lower_constructor_sets import lower
from label_composed_witnesses import target


def samples(recipe,count,seed):
    rng=np.random.default_rng(seed);rules=recipe['rules'];width=max(len(a['args']) for r in rules for a in r['query']);atoms=max(len(r['query']) for r in rules)
    xs=[];edges=[];masks=[];requests=[];ys=[];targets=[];rids=[];source_targets=[]
    for rid,rule in enumerate(rules):
        roles,request=template(rule)
        occurrences={}
        for ai,a in enumerate(rule['query']):
            for fi,arg in enumerate(a['args']):
                if 'slot' not in arg:raise ValueError('candidate generator currently requires slot query arguments')
                occurrences.setdefault(arg['slot'],[]).append((ai,fi))
        repeats=[v for v in occurrences.values() if len(v)>1]
        for example in range(count):
            values={}
            for slot,uses in occurrences.items():
                sort=rule['slots'][slot]['sort']
                if sort['kind']=='eq':
                    pool=[v for v in values.values() if v['sort']==sort['name'] and 'eq' in v]
                    value=dict(pool[int(rng.integers(len(pool)))]) if pool and rng.random()<.25 else dict(sort=sort['name'],eq='v'+str(slot))
                elif sort['kind']=='i64':value=dict(sort=sort['name'],value=int(rng.integers(-4,9)))
                elif sort['kind']=='String':value=dict(sort=sort['name'],value='s'+str(rng.integers(0,12)))
                else:raise ValueError('unsupported synthetic scalar '+str(sort))
                values[slot]=value
            rows=[dict(table=a['call']['table'],values=[dict(values[x['slot']]) for x in a['args']],subsumed=False) for a in rule['query']]
            if example%2 and repeats:
                uses=repeats[int(rng.integers(len(repeats)))];ai,fi=uses[-1];old=rows[ai]['values'][fi]
                rows[ai]['values'][fi]=dict(old,eq='broken') if 'eq' in old else dict(old,value=old['value']+100 if isinstance(old['value'],int) else old['value']+'!')
            # Canonical constructor identity is authoritative even for negatives.
            ids={};seed_values={}
            for row in rows:
                for v in row['values']:
                    key=identity(v)
                    if key not in ids:ids[key]=len(ids);seed_values[ids[key]]=v
            ref=Reference(recipe,[],ids)
            for row in rows:
                v=[ids[identity(x)] for x in row['values']];ref.construct(row['table'],v[:-1],v[-1])
            ref.close();binding={};valid=True
            for a,row in zip(rule['query'],rows):
                for arg,v in zip(a['args'],row['values']):
                    s=arg['slot'];value=ref.root(ids[identity(v)])
                    if s in binding and binding[s]!=value:valid=False
                    binding[s]=value
            x=np.zeros((atoms,width*128),np.float32);edge=np.zeros((atoms,atoms,64),np.float32);mask=np.zeros(atoms,bool);port_roles=[];source_code=np.zeros((atoms,128),np.float32)
            for ai,(a,row) in enumerate(zip(rule['query'],rows)):
                schema=next(t['schema'] for t in recipe['tables'] if t['name']==row['table'])
                seed_rule=dict(slots=[dict(sort=s,definition='query') for s in schema],query=[dict(call=a['call'],args=[dict(slot=i) for i in range(len(schema))])],effects=[])
                pr,_=template(seed_rule);port_roles.append(pr);mask[ai]=True
                source_code[ai]=encode([(fi,v,(v['sort'],ref.root(ids[identity(v)])) if 'eq' in v else None) for fi,v in enumerate(row['values'])],pr,'class-balanced')
                for fi,v in enumerate(row['values']):
                    current=ref.root(ids[identity(v)])
                    context=sum((pr[j] for j,w in enumerate(row['values']) if ref.root(ids[identity(w)])==current),np.zeros(64,np.float32)) if 'eq' in v else scalar(v)
                    x[ai,fi*128:(fi+1)*128]=np.concatenate([pr[fi],np.tanh(context)])
            for ai,row in enumerate(rows):
                for bi,other in enumerate(rows):
                    terms=[port_roles[ai][fi]*port_roles[bi][fj] for fi,v in enumerate(row['values']) for fj,w in enumerate(other['values']) if v['sort']==w['sort'] and ref.root(ids[identity(v)])==ref.root(ids[identity(w)])]
                    if terms:edge[ai,bi]=np.sum(terms,axis=0)/np.sqrt(len(terms))
            out=np.zeros(128,np.float32)
            if valid:
                ref.apply([rule]);lowered,_=lower(dict(recipe,rules=[rule]));lr=lowered['rules'][0]
                slots=np.full(len(lr['slots']),-1,np.int32)
                for s,v in binding.items():slots[s]=v
                out,_=target(lr,slots,{i:ref.root(i) for i in range(len(ids))},ref,seed_values,len(lr['slots']))
            source_targets.append(source_code);xs.append(x);edges.append(edge);masks.append(mask);requests.append(request);ys.append(valid);targets.append(out);rids.append(rid)
    return dict(source_target=np.array(source_targets),x=np.array(xs),edges=np.array(edges),mask=np.array(masks),request=np.array(requests),valid=np.array(ys,np.float32),target=np.array(targets),rule=np.array(rids,np.int32))
