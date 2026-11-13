#!/usr/bin/env python3
"""Account for completed-source bindings replaced by already-live Cell ports."""
import json
import sys
from pathlib import Path

b, a, bh, ah = (json.loads(Path(p).read_text()) for p in sys.argv[1:5])
assert b['all_saved_run_checks_equal'] is True and a['all_saved_run_checks_equal'] is True
for key in ('program_sha256','runs','final_state','parent_takeover','shared_owners','diagnostic_compaction'):
    assert b[key] == a[key], key
for key in ('program_sha256','runs','mode','final_state_sha256'):
    assert bh[key] == ah[key], key
assert b['program_sha256'] == bh['program_sha256']
assert b['runs'] == bh['runs']
assert bh['port_index']['birth_hints_enabled'] == ah['port_index']['birth_hints_enabled']
source = ('explicit_cell_slots','cell_slot_bytes','writer_bytes','parent_links','completed_owner_frames','cell_fact_arities')
heap = ('graph_owned_teardown_bytes','retained_program_teardown_bytes','execution_and_takeover_peak_bytes','net_growth_over_setup_bytes','max_takeover_extra_bytes')
changed = {k:[b['graph_work'].get(k),a['graph_work'].get(k)]
           for k in sorted(b['graph_work'].keys() | a['graph_work'].keys())
           if b['graph_work'].get(k) != a['graph_work'].get(k)}
result = {'scope':'actual standalone Cell runtime; requested heap, not RSS or speed',
    'program_sha256':a['program_sha256'],'runs':a['runs'],'all_saved_run_checks_equal':True,
    'source_storage':{k:[b['source_storage'][k],a['source_storage'][k]] for k in source},
    'live_source_frames':[r['source_storage']['completed_owners']['source_records'] + r['source_storage']['completed_owner_frames'] for r in (b,a)],
    'graph_work_changes':changed,'heap':{k:[bh[k],ah[k]] for k in heap},
    'net_graph_and_program_saved_bytes':sum(bh[k]-ah[k] for k in heap[:2]),
    'limitations':['New per-completion equality checks are charged, not assumed free.',
        'Cumulative removed slots differ from final live slot reduction.',
        'Stable fact identity, source descriptors and necessary boundary indices remain.',
        'No large whole-egraph compression or timing claim.']}
Path(sys.argv[5]).write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
