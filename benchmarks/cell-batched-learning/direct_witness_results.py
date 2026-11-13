"""Report guarded direct witness work against the unchanged seed kernel."""
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
rows = []
for name in ('fact', 'loopfact', 'sum-bits', 'dot-product'):
    before = json.loads((root/name/'candidate-owned-fact-heap.json').read_text())
    seed = json.loads((root/name/'candidate.json').read_text())
    candidate = json.loads((root/'witness-direct'/name/'candidate.json').read_text())
    seed.pop('sha256'); candidate.pop('sha256'); candidate.pop('ownership_witnesses')
    assert seed == candidate, 'only the witness catalog may differ'
    directory = root/'witness-direct'/name
    earlier = json.loads((directory/'heap.json').read_text())
    after = json.loads((directory/'heap-dispatch.json').read_text())
    assert before['final_state_sha256'] == after['final_state_sha256'] == earlier['final_state_sha256']
    counts = after['completion_work']
    stats = {k:v for k,v in counts.items() if 'cell_route' in k}
    stats['route_probes_before_operation_dispatch'] = earlier['completion_work']['constructor_cell_route_probes']
    stats['additional_prepared_field_checks'] = counts['constructor_prepared_fields'] - before['completion_work']['constructor_prepared_fields']
    stats['port_key_lookups_before'] = before['port_index']['stats']['key_lookups']
    stats['port_key_lookups_after'] = after['port_index']['stats']['key_lookups']
    rows.append(dict(case=name, baseline_program=before['program_sha256'], candidate_program=after['program_sha256'],
                     graph_before=before['graph_owned_teardown_bytes'], graph_after=after['graph_owned_teardown_bytes'],
                     program_bytes_added=after['retained_program_teardown_bytes']-before['retained_program_teardown_bytes'],
                     work=stats, same_final_state=True))
Path(sys.argv[2]).write_text(json.dumps(dict(scope='standalone Cell runtime; explicit optional witness catalog; work and memory, not speed',
                                           cases=rows), indent=2)+'\n')
