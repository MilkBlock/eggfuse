"""Summarize saved executions; never treat overlapping Bake credit as savings."""
import json
import sys
from pathlib import Path

root, output = map(Path, sys.argv[1:])
def read(name):
    return json.loads((root / name).read_text())

base = read('completed-symbolic-heap.json')
rows = {}
for label, path in [('baseline', 'completed-symbolic-heap.json'),
                    ('unit_facts', 'unit-facts-heap.json'),
                    ('unit_owned', 'unit-owned-mapped-heap.json'),
                    ('unit_owned_bake4', 'unit-owned-bake/frames4/heap.json')]:
    data = read(path)
    assert data['final_state_sha256'] == base['final_state_sha256']
    rows[label] = {key: data[key] for key in (
        'program_sha256', 'runs', 'graph_owned_teardown_bytes',
        'retained_program_teardown_bytes', 'execution_and_takeover_peak_bytes',
        'max_takeover_extra_bytes', 'final_state_sha256')}
    rows[label]['graph_delta_from_baseline'] = (
        data['graph_owned_teardown_bytes'] - base['graph_owned_teardown_bytes'])
audits = {}
for label, path in [('unit_facts', 'unit-facts-audit.json'),
                    ('unit_owned', 'unit-owned-mapped-audit.json')]:
    data = read(path)
    for key in ['source_specialization_verified', 'baseline_saved_checks_equal',
                'graph_rhs_writes_equal']:
        assert data[key] is True, (label, key)
    audits[label] = {key: data[key] for key in (
        'runs', 'write_comparison', 'source_specialization_verified',
        'baseline_saved_checks_equal', 'graph_rhs_writes_equal', 'resume_changed_runs')}
    audits[label]['physical_write_changed_run_count'] = len(data['physical_write_changed_runs'])
result = {'scope': 'actual standalone Cell runtime; not native egglog; requested allocation bytes, not RSS',
          'admission': 'all candidates rejected for baseline replacement: Graph memory regresses',
          'heap': rows, 'run_audits': audits, 'offline_bake': read('unit-owned-bake/summary.json'),
          'limits': ['Bake4 has final-state equality only, no full Run audit',
                     'Bake8 and Bake16 have not executed',
                     'candidate ranking scores overlap and are not additive savings']}
output.write_text(json.dumps(result, indent=2) + '\n')
