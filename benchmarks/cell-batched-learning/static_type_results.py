"""Charge executed static type guards, separately from lookup or memory savings."""
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
cases = []
for name in ('fact', 'loopfact', 'sum-bits', 'dot-product'):
    directory = root / name
    before = json.loads((directory / 'candidate-atomic-heap.json').read_text())
    after = json.loads((directory / 'candidate-static-types-heap.json').read_text())
    assert before['program_sha256'] == after['program_sha256']
    assert before['final_state_sha256'] == after['final_state_sha256']
    assert before['source_storage']['fact_lifecycle'] == after['source_storage']['fact_lifecycle']
    assert before['graph_fields'] == after['graph_fields']
    work = after['ownership_query_work']
    static = work['domain_static_type_guards']
    total = work['domain_type_guards']
    assert 0 <= static <= total
    cases.append(dict(case=name, program=after['program_sha256'],
        candidate_type_guards=total, static_type_guards=static,
        instance_directory_type_reads_avoided=static,
        dynamic_type_guards=total-static,
        compiled_layout_operator_bytes=dict(after['program_fields'])['ownership.layout_operators'],
        graph_bytes=after['graph_owned_teardown_bytes'], graph_fields_unchanged=True,
        final_state_and_fact_lifecycle_equal=True))
Path(sys.argv[2]).write_text(json.dumps(dict(
    scope='actual standalone Cell runtime; executed candidate type dispatch, not timings',
    limitation='Each static guard replaces one type-dispatch directory read. It does not remove constructor queries, live-node checks, directories, facts, or instances. Ambiguous layouts use concrete instance code.',
    cases=cases), indent=2)+'\n')
