"""Separate proved RHS-key work from existing witness lookup savings."""
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
cases = []
for name in ('fact', 'loopfact', 'sum-bits', 'dot-product'):
    directory = root/'witness-direct'/name
    before = json.loads((directory/'heap-dispatch.json').read_text())
    after = json.loads((directory/'heap-key-proof.json').read_text())
    current_seed = json.loads((root/name/'candidate-stage-inherited-heap.json').read_text())
    assert before['program_sha256'] == after['program_sha256']
    assert before['final_state_sha256'] == after['final_state_sha256'] == current_seed['final_state_sha256']
    assert after['source_storage']['fact_lifecycle'] == current_seed['source_storage']['fact_lifecycle']
    old, work = before['completion_work'], after['completion_work']
    for counter in ('constructor_cell_route_probes', 'constructor_cell_route_witnesses', 'constructor_cell_route_accepted'):
        assert old[counter] == work[counter], counter
    assert before['port_index']['stats']['key_lookups'] == after['port_index']['stats']['key_lookups']
    avoided = work['constructor_cell_route_key_fields_avoided']
    assert old['constructor_prepared_fields'] - work['constructor_prepared_fields'] == avoided
    assert current_seed['graph_owned_teardown_bytes'] == after['graph_owned_teardown_bytes']
    cases.append(dict(case=name, key_constructions_removed=work['constructor_cell_route_key_proved'],
        key_fields_not_constructed=avoided, repeated_target_field_checks_removed=avoided,
        source_liveness_checks=work['constructor_cell_route_source_checks'],
        proof_admissions=work['constructor_cell_route_proof_admissions'],
        proof_admissions_falling_back=work['constructor_cell_route_proof_admissions']-work['constructor_cell_route_key_proved'],
        route_probes=work['constructor_cell_route_probes'], route_accepted=work['constructor_cell_route_accepted'],
        graph_bytes=after['graph_owned_teardown_bytes'], graph_equal_to_current_seed=True,
        exact_lifecycle_trace_equal=True, final_state_equal=True))
Path(sys.argv[2]).write_text(json.dumps(dict(scope='actual standalone Cell runtime; optional constructor witness catalog, not a speed measurement',
    limitations='Existing index lookups saved by witness routes are not counted again. The default shared seed is unchanged. No additional runtime compression.',
    cases=cases),indent=2)+'\n')
