#!/usr/bin/env python3
"""Charge candidate selection against generic query reductions and storage."""
import json
import sys
from pathlib import Path

def collect(root,programs):
    rows=[]
    for case in ('fact','loopfact','sum-bits','dot-product'):
        a,b=[json.loads((root/f'{case}-{mode}.json').read_text()) for mode in ('seed','multi')]
        seed=json.loads((programs/case/'candidate.json').read_text())
        candidate=json.loads((programs/'witness-multi'/case/'candidate.json').read_text())
        for raw in (seed,candidate):raw.pop('sha256')
        candidate.pop('ownership_witnesses')
        if seed!=candidate:raise ValueError('changed source beyond witness catalog')
        if a['final_state_sha256']!=b['final_state_sha256'] or a['runs']!=b['runs']:raise ValueError('state mismatch')
        counts=b['completion_work']
        rows.append(dict(case=case,seed_program=a['program_sha256'],candidate_program=b['program_sha256'],runs=b['runs'],same_final_state=True,
            graph_before=a['graph_owned_teardown_bytes'],graph_after=b['graph_owned_teardown_bytes'],
            program_bytes_added=b['retained_program_teardown_bytes']-a['retained_program_teardown_bytes'],
            port_key_lookups_before=a['port_index']['stats']['key_lookups'],port_key_lookups_after=b['port_index']['stats']['key_lookups'],
            route_work={k:v for k,v in counts.items() if 'constructor_cell_route' in k},
            prepared_field_delta=counts['constructor_prepared_fields']-a['completion_work']['constructor_prepared_fields']))
    return dict(scope='Same-binary standalone Cell runtime, installed witness catalogs versus no catalog; no timing claim',cases=rows)
if __name__=='__main__':
    d=collect(Path(sys.argv[1]),Path(sys.argv[2]));Path(sys.argv[3]).write_text(json.dumps(d,indent=2)+'\n')
    for r in d['cases']:print(r['case'],r['port_key_lookups_before'],r['port_key_lookups_after'],r['route_work'])
