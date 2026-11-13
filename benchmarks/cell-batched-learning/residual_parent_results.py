"""Account for residual inherited values, parent release, and owner transfer."""
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
rows = []
for name in ('fact', 'loopfact', 'sum-bits', 'dot-product'):
    d = root/name
    before = json.loads((d/'candidate-owned-fact-heap.json').read_text())
    after = json.loads((d/'candidate-residual-parent-heap.json').read_text())
    assert before['program_sha256'] == after['program_sha256']
    assert before['final_state_sha256'] == after['final_state_sha256']
    states = []
    for report in (before, after):
        storage = report['source_storage']
        frames = storage['fact_lifecycle']['frames']
        states.append(dict(graph_bytes=report['graph_owned_teardown_bytes'],
                           parent_edges=storage['parent_links'],
                           source_records=storage['completed_owners']['source_records'],
                           logical_frames=len(frames), logical_facts=sum(len(f['facts']) for f in frames),
                           explicit_slots=storage['explicit_cell_slots'],
                           execution_peak=report['execution_and_takeover_peak_bytes'],
                           takeover_temporary_peak=report['max_takeover_extra_bytes']))
    rows.append(dict(case=name, source_program=after['program_sha256'], before=states[0], after=states[1],
                     graph_bytes_saved=states[0]['graph_bytes']-states[1]['graph_bytes'],
                     residual_slots_captured=after['completion_work']['completed_parent_residual_slots'],
                     residual_capacity_growth_bytes=after['completion_work']['completed_parent_residual_capacity_bytes'],
                     parent_detachments=after['completion_work']['completed_parent_detachments'],
                     final_state_equal=True))
Path(sys.argv[2]).write_text(json.dumps(dict(scope='actual standalone Cell runtime, unchanged shared catalog; no speed claim',
    limits='logical source identities and live facts remain; execution peak includes Program and executor; cumulative capture work is not final retained storage',
    cases=rows), indent=2)+'\n')
