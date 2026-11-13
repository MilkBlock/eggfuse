"""Account for actual completed-fact stage inheritance, including all overhead."""
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
cases = []
for name in ('fact', 'loopfact', 'sum-bits', 'dot-product'):
    directory = root/name
    before = json.loads((directory/'candidate-residual-parent-heap.json').read_text())
    after = json.loads((directory/'candidate-stage-inherited-heap.json').read_text())
    assert before['program_sha256'] == after['program_sha256']
    assert before['final_state_sha256'] == after['final_state_sha256']
    assert before['source_storage']['fact_lifecycle'] == after['source_storage']['fact_lifecycle']
    def measured(report):
        storage = report['source_storage']
        return dict(graph_bytes=report['graph_owned_teardown_bytes'],
                    fact_capacity_bytes=storage['fact_record_capacity_bytes'],
                    fact_live_bytes=storage['fact_record_live_bytes'],
                    owner_headers_bytes=storage['completed_owner_records_bytes'],
                    execution_and_takeover_peak=report['execution_and_takeover_peak_bytes'],
                    max_takeover_extra=report['max_takeover_extra_bytes'])
    cases.append(dict(case=name, before=measured(before), after=measured(after),
        graph_bytes_saved=before['graph_owned_teardown_bytes']-after['graph_owned_teardown_bytes'],
        inherited_lifecycles=after['source_storage']['completed_owners']['inherited_fact_lifecycles'],
        live_owned_facts=after['source_storage']['completed_owners']['live_fact_entries'],
        exact_lifecycle_trace_equal=True, final_state_equal=True))
Path(sys.argv[2]).write_text(json.dumps(dict(scope='actual standalone Cell runtime; stage metadata inheritance, not fact elimination',
    limitations='Graph teardown includes all fields; process peak includes Program and executor. No speed claim or nested-template execution claim.',
    cases=cases),indent=2)+'\n')
