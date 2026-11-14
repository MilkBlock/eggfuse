"""Construct checked synthetic completed producer frames, without future matches.

Logical provenance is preserved; physical ownership is initially independent.
This is a synthetic initialization, not proof of original program reachability.
"""
import numpy as np
from enumerate_cell_interactions import replay_case
from synthetic_cell_inputs import validate
from lower_constructor_sets import lower
from lower_query_literals import lower as lower_literals
from device_snapshot_import import prepare_family,identity
from device_semantic_template import semantic,template
from multi_entry_ridge import encode,scalar


def prepare(document,spare):
    recipe,snapshot=validate(document)
    if document['schema']!='enumerated-cell-input/v1':raise ValueError('enumeration required')
    if document['case'].get('producer_phase','completed')!='completed':raise ValueError('completed producer frames require completed phase')
    _,interface=replay_case(recipe,document['case'],with_interface=True)
    lowered,_=lower(lower_literals(recipe))
    if any(r.get('query_literal_guards') for r in lowered['rules']):raise ValueError('producer literal slots need explicit binding support')
    local,state,ids,rows=prepare_family(lowered,snapshot,list(range(len(recipe['rules']))),spare+interface.producer_count)
    producers=document['case']['producer'];producers=producers if isinstance(producers,list) else [producers]
    frames=[];seen={};covered=set()
    for owner,rid in enumerate(producers):
        rule=local['rules'][rid];source,projection=semantic(rule)
        side='p' if len(producers)==1 else 'p'+str(owner)
        values=[]
        for slot in projection:
            value=interface.slot_values.get((side,slot))
            if value is None or identity(value) not in ids:raise ValueError('unrepresented producer slot')
            values.append(value)
        for name,args in [f for f,o in zip(interface.exports,interface.export_owners) if o==owner]:
            covered.add((name,tuple(identity(interface.slot_values[a]) for a in args)))
        query=[i for i,s in enumerate(rule['slots']) if s['definition']=='query']
        key=(rid,*(ids[identity(values[i])] for i in query))
        if key in seen:
            prior=seen[key]
            if prior['values']!=values:raise ValueError('same producer key has different payload')
            frames.append(prior);continue
        frame=dict(rule=rid,values=values,key=key,row=len(rows)+len(seen));seen[key]=frame;frames.append(frame)
    for frame in seen.values():
        row=frame['row'];rid=frame['rule'];rule=local['rules'][rid]
        state['keys'][row,:len(frame['key'])]=frame['key'];state['generation'][row]=1
        for field in ('present','visible','settled'):state[field][row]=True
        state['effect_pc'][row]=len(rule['effects']);encoded=[]
        for slot,value in enumerate(frame['values']):
            label=ids[identity(value)]
            state['slots'][row,slot]=state['slot_roots'][row,slot]=label;state['slot_valid'][row,slot]=True
            eq=(value['sort'],value['eq']) if 'eq' in value else None
            encoded.append((slot,value,eq))
            if eq is None:
                state['scalar_codes'][row,slot]=scalar(value);state['scalar_valid'][row,slot]=True
        roles,_=template(rule);source,_=semantic(rule)
        state['tokens'][row]=encode([v for v in encoded if v[0]<len(source['slots'])],roles,'class-balanced')
    # Facts covered by completed frames are exposed through their ordinary views.
    # Keep only uncovered boundary seed rows; no duplicate side fact registry.
    for row,fact in enumerate(rows):
        if (fact['table'],tuple(identity(v) for v in fact['values'])) in covered:
            for field in ('present','visible','settled'):state[field][row]=False
    verify_views(local,state,ids,rows)
    return local,state,ids,rows,dict(producer_rows=[f['row'] for f in frames],distinct_frames=len(seen),retained_boundary_rows=int(state['present'][:len(rows)].sum()),scope='synthetic completed producer frames; no physical transfer or reachability claim')


def verify_views(recipe,state,ids,rows):
    from device_witness_views import compile_view,project
    from device_slot_owners import pack
    expected={(r['table'],tuple(ids[identity(v)] for v in r['values'])) for r in rows}
    actual=set();packed=pack(state)
    for tid,table in enumerate(recipe['tables']):
        if table['kind']!='constructor':continue
        v=project(packed,compile_view(recipe,tid,len(table['schema'])-1),True,True,np,include_fields=True)
        if not bool(v['complete']):raise ValueError('producer view incomplete')
        actual.update((table['name'],tuple(map(int,row))) for row in v['value_roots'][v['live']])
    if actual!=expected:raise ValueError('producer frames change visible facts')


def main():
    import argparse,json,hashlib
    from pathlib import Path
    p=argparse.ArgumentParser();p.add_argument('enumeration',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    manifest=json.loads((a.enumeration/'manifest.json').read_text());recipe=manifest['recipe']
    counts=dict(cases=0,producer_instances=0,distinct_frames=0,retained_boundary_rows=0)
    for line in (a.enumeration/'cases.jsonl').open():
        case=json.loads(line)
        doc=dict(schema='enumerated-cell-input/v1',recipe=recipe,recipe_sha256=manifest['recipe_sha256'],case=case,snapshot=case['snapshot'],input_sha256=case['input_sha256'])
        _,_,_,_,r=prepare(doc,4)
        counts['cases']+=1;counts['producer_instances']+=len(r['producer_rows'])
        for k in ('distinct_frames','retained_boundary_rows'):counts[k]+=r[k]
        if counts['cases']%2000==0:print(counts,flush=True)
    report=dict(scope='all enumerated routes materialized as synthetic producer frames; exact projected facts preserved; not a rollout or ownership transfer benchmark',counts=counts,cases_sha256=hashlib.sha256((a.enumeration/'cases.jsonl').read_bytes()).hexdigest(),passed=True)
    a.output.write_text(json.dumps(report,indent=2)+'\n');print(report)
if __name__=='__main__':main()
