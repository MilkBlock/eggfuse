"""Charge trace-selected Unit ownership against the accepted baseline."""
import json
import sys
from pathlib import Path
r, output = map(Path, sys.argv[1:])
def read(name):
    return json.loads((r / name).read_text())
b, a = read('completed-symbolic-heap.json'), read('unit-selected-heap.json')
audit, program = read('unit-selected-audit.json'), read('unit-selected-program.json')
control = read('unit-selected-control-heap.json')
assert control['final_state_sha256'] == a['final_state_sha256']
assert a['program_sha256'] == audit['program_sha256'] == program['sha256']
assert audit['base_program'] == b['program_sha256']
assert a['final_state_sha256'] == b['final_state_sha256']
assert a['runs'] == b['runs'] == audit['runs']
for key in ['source_specialization_verified', 'baseline_saved_checks_equal', 'graph_rhs_writes_equal']:
    assert audit[key] is True
metrics = ['graph_owned_teardown_bytes', 'retained_program_teardown_bytes',
           'execution_and_takeover_peak_bytes', 'max_takeover_extra_bytes']
fields = {}
for kind in ['graph_fields', 'program_fields']:
    bv, av = dict(b[kind]), dict(a[kind])
    fields[kind] = {k: av.get(k, 0)-bv.get(k, 0) for k in sorted(bv.keys() | av.keys())
                    if av.get(k, 0) != bv.get(k, 0)}
result = dict(scope='actual standalone Cell runtime, requested allocation bytes; no timing claim',
    base_program=b['program_sha256'], candidate=a['program_sha256'], runs=a['runs'],
    tables=[dict(id=i, name=program['source_core']['tables'][i]['name'])
            for i in program['unit_fact_specialization']['tables']],
    migration=program['ownership_fragments']['selection_provenance'],
    control=dict(program=control['program_sha256'],
        graph_owned_teardown_bytes=control['graph_owned_teardown_bytes'],
        retained_program_teardown_bytes=control['retained_program_teardown_bytes'],
        graph_reduction_from_selected_tables=b['graph_owned_teardown_bytes']-control['graph_owned_teardown_bytes'],
        additional_graph_reduction_from_learned_catalog=control['graph_owned_teardown_bytes']-a['graph_owned_teardown_bytes'],
        scope='same selected tables, old catalog; final-state equality only, no full Run audit'),
    heap={k: dict(before=b[k], after=a[k], delta=a[k]-b[k]) for k in metrics},
    graph_reduction_fraction=1-a['graph_owned_teardown_bytes']/b['graph_owned_teardown_bytes'],
    net_graph_and_program_delta=sum(a[k]-b[k] for k in metrics[:2]),
    field_deltas=fields,
    audit={k:audit[k] for k in ['source_specialization_verified','baseline_saved_checks_equal',
                              'graph_rhs_writes_equal','resume_changed_runs','write_comparison']},
    physical_write_changed_runs=len(audit['physical_write_changed_runs']),
    admission='Graph compression only; retained Program and process peak regress; baseline unchanged')
output.write_text(json.dumps(result, indent=2)+'\n')
