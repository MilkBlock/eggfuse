"""Attribute production memory changes solely to explicit observation history."""
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
cases = []
for name in ('fact', 'loopfact', 'sum-bits', 'dot-product'):
    directory = root/name
    before = json.loads((directory/'candidate-stage-inherited-heap.json').read_text())
    after = json.loads((directory/'candidate-explicit-history-heap.json').read_text())
    assert before['program_sha256'] == after['program_sha256']
    assert before['final_state_sha256'] == after['final_state_sha256']
    assert before['source_storage']['fact_lifecycle'] == after['source_storage']['fact_lifecycle']
    old_fields, new_fields = dict(before['graph_fields']), dict(after['graph_fields'])
    saved = old_fields.pop('ownership.barriers')
    assert new_fields.pop('ownership.barriers') == 0
    assert old_fields == new_fields, 'unrelated Graph fields changed'
    assert before['graph_owned_teardown_bytes']-after['graph_owned_teardown_bytes'] == saved
    cases.append(dict(case=name, source_program=after['program_sha256'],
        graph_before=before['graph_owned_teardown_bytes'], graph_after=after['graph_owned_teardown_bytes'],
        diagnostic_history_bytes_removed=saved,
        process_peak_before=before['execution_and_takeover_peak_bytes'],
        process_peak_after=after['execution_and_takeover_peak_bytes'],
        exact_lifecycle_trace_equal=True, final_state_equal=True))
Path(sys.argv[2]).write_text(json.dumps(dict(scope='actual standalone Cell runtime, ordinary non-audit execution; explicit tracing still retains history',
    limitations='Removes default diagnostic history, not logical facts or instance fields. Process peaks include Program and executor. No speed claim.',
    cases=cases),indent=2)+'\n')
