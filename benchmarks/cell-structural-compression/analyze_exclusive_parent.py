#!/usr/bin/env python3
"""Reject a local takeover proof when the actual heap lane gives no saving."""
import json
import sys
from pathlib import Path
b,a=(json.loads(Path(p).read_text()) for p in sys.argv[1:3])
for key in ('program_sha256','mode','runs','final_state_sha256'):
    assert b[key]==a[key],key
assert b['port_index']['birth_hints_enabled']==a['port_index']['birth_hints_enabled']
keys=('graph_owned_teardown_bytes','retained_program_teardown_bytes',
    'execution_and_takeover_peak_bytes','net_growth_over_setup_bytes','max_takeover_extra_bytes')
result={'scope':'actual standalone Cell runtime allocation lane; not timing or full Run-boundary acceptance',
    'program_sha256':a['program_sha256'],'runs':a['runs'],'final_state_equal':True,
    'heap':{k:[b[k],a[k]] for k in keys},
    'ordinary_source_records':[len(r['ownership_storage']['source_eq_bindings']) for r in (b,a)],
    'graph_field_changes':{k:[dict(b['graph_fields']).get(k),v] for k,v in a['graph_fields'] if dict(b['graph_fields']).get(k)!=v},
    'net_retained_growth':sum(a[k]-b[k] for k in keys[:2]),
    'admission':'rejected; experimental runtime patch not applied',
    'limits':['Local regression proves source retirement, not workload coverage.',
        'Unchanged final heap does not prove the path never ran.',
        'No new per-Run semantic acceptance was run for this rejected experiment.']}
Path(sys.argv[3]).write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
