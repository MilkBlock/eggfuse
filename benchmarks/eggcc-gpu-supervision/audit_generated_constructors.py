"""CPU structural audit for fresh constructor identities, independent of allocation order.

Only immutable slot-argument constructs and copies are covered. Seed identities
are opaque exact atoms; fresh identities must form a bijection with constructed
terms. This is not native Eq proof replay or a union/subsume verifier.
"""
import numpy as np
from device_snapshot_import import identity
from device_slot_owners import read


def without_rhs_tables(rule,snapshot):
    query={a['call']['table'] for a in rule['query']}
    effects={o['call']['table'] for o in rule['effects'] if o['kind']=='construct'}
    removed=effects-query
    rows=[r for r in snapshot['rows'] if r['table'] not in removed]
    return dict(snapshot,rows=rows),sorted(removed),len(snapshot['rows'])-len(rows)


def audit(rule,rows,ids,state,indices,next_id):
    top=len(ids);lookup={};actual_terms={i:('seed',i) for i in range(top)};term_ids={v:k for k,v in actual_terms.items()}
    destinations=[o['dst'] for o in rule['effects']]
    inputs=[i for i,s in enumerate(rule['slots']) if s['definition']=='query']
    if len(set(destinations))!=len(destinations) or set(inputs)&set(destinations):raise ValueError('audit requires retained effect slots')
    for row in rows:
        fields=[('seed',ids[identity(v)]) for v in row['values']]
        address=(row['table'],tuple(fields[:-1]))
        if address in lookup and lookup[address]!=fields[-1]:raise ValueError('conflicting constructor seed')
        lookup[address]=fields[-1]
    wrong=0;checked=0;problems=[]
    for index in indices:
        expected={s:('seed',int(v)) for s,v in zip(inputs,state['keys'][index,1:])}
        actual={s:int(v) for s,v in zip(inputs,state['keys'][index,1:])}
        bad=[(-1,'unknown_input_identity') for value in actual.values() if not 0<=value<top]
        for oi,op in enumerate(rule['effects']):
            if op['kind']=='copy':
                term=expected[op['arg']['slot']];wanted=actual[op['arg']['slot']]
            elif op['kind']=='construct':
                address=(op['call']['table'],tuple(expected[a['slot']] for a in op['args']))
                term=lookup.setdefault(address,('construct',*address));wanted=term_ids.get(term)
            else:raise ValueError('unsupported structural audit effect')
            dst=op['dst'];value=int(read(state,'slots',np.array(index),np.array(dst),np))
            root=int(read(state,'slot_roots',np.array(index),np.array(dst),np));valid=bool(read(state,'slot_valid',np.array(index),np.array(dst),np))
            if not valid or root!=value or not 0<=value<next_id:bad.append((oi,'invalid_result'))
            if wanted is not None and wanted!=value:bad.append((oi,'wrong_reuse_or_copy'))
            if value in actual_terms and actual_terms[value]!=term:bad.append((oi,'identity_aliases_distinct_terms'))
            if term in term_ids and term_ids[term]!=value:bad.append((oi,'duplicate_constructor_identity'))
            if value not in actual_terms and value>=top and valid:
                actual_terms[value]=term;term_ids.setdefault(term,value)
            expected[dst]=term;actual[dst]=value
        # Query slots also retain their original bindings.
        for slot in inputs:
            if not bool(read(state,'slot_valid',np.array(index),np.array(slot),np)) or int(read(state,'slots',np.array(index),np.array(slot),np))!=actual[slot]:bad.append((-1,'changed_input'))
        checked+=1;wrong+=bool(bad)
        if bad:problems.append(dict(row=int(index),reasons=bad))
    allocated=set(range(top,int(next_id)));observed={v for v in actual_terms if v>=top}
    missing=allocated-observed
    return dict(checked=checked,wrong=int(wrong),fresh_terms=len(observed),unexplained_allocations=len(missing),passed=wrong==0 and not missing,problems=problems)
