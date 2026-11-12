#!/usr/bin/env python3
"""Charge observed owner extensions against the complete Graph and retained Program."""
import json
import sys
from pathlib import Path

before_a, after_a, before_h, after_h, output = map(Path, sys.argv[1:])
b, a, bh, ah = (json.loads(p.read_text()) for p in (before_a, after_a, before_h, after_h))
assert b['all_saved_run_checks_equal'] is True and a['all_saved_run_checks_equal'] is True
assert b['final_state'] == a['final_state']
assert bh['final_state_sha256'] == ah['final_state_sha256']
assert b['runs'] == a['runs'] == bh['runs'] == ah['runs']
assert b['program_sha256'] == bh['program_sha256'] and a['program_sha256'] == ah['program_sha256']
for key in ('parent_takeover', 'shared_owners', 'diagnostic_compaction'):
    assert a[key] == b[key]
for key in ('mode',):
    assert ah[key] == bh[key]
assert bh['port_index']['birth_hints_enabled'] == ah['port_index']['birth_hints_enabled']
metrics = ('graph_owned_teardown_bytes', 'retained_program_teardown_bytes',
           'execution_and_takeover_peak_bytes', 'net_growth_over_setup_bytes', 'max_takeover_extra_bytes')
source = ('explicit_cell_slots', 'parent_links', 'cell_slot_bytes', 'cell_records_bytes',
          'completed_owner_records_bytes', 'completed_owner_frames', 'fact_record_capacity_bytes',
          'fact_record_live_bytes', 'writer_count', 'writer_bytes')
net = sum(ah[k]-bh[k] for k in metrics[:2])
result = {'scope': 'actual standalone Cell runtime; requested heap, not RSS or speed',
    'programs': [b['program_sha256'], a['program_sha256']], 'runs': a['runs'],
    'all_saved_run_checks_equal': True, 'final_state_equal': True,
    'heap': {k:[bh[k],ah[k]] for k in metrics}, 'net_graph_and_program_growth_bytes': net,
    'live_components': [len(h['ownership_storage']['components']) for h in (bh, ah)],
    'live_source_frames': [r['source_storage']['completed_owners']['source_records'] + r['source_storage']['completed_owner_frames'] for r in (b, a)],
    'source_storage': {k:[b['source_storage'][k],a['source_storage'][k]] for k in source},
    'graph_field_changes': {k:[dict(bh['graph_fields']).get(k,0),v] for k,v in ah['graph_fields'] if dict(bh['graph_fields']).get(k,0)!=v},
    'admission': 'reject-net-retained-memory-growth' if net>0 else 'requires-review',
    'limitations': ['Reduced component count is not a count of retired facts or instances.',
        'Process execution peak is not a Graph-exclusive within-Run peak.',
        'Retained Program costs include selection provenance and compiled plans.']}
output.write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(result, indent=2))
