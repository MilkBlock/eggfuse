"""Measure removed stable records against the same typed-dispatch seed."""
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
rows = []
for case in ('fact', 'loopfact', 'sum-bits', 'dot-product'):
    d = root/case
    a = json.loads((d/'candidate-static-types-heap.json').read_text())
    b = json.loads((d/'candidate-template-fields-heap.json').read_text())
    assert a['program_sha256'] == b['program_sha256']
    assert a['final_state_sha256'] == b['final_state_sha256']
    assert a['source_storage']['fact_lifecycle'] == b['source_storage']['fact_lifecycle']
    af, bf = dict(a['graph_fields']), dict(b['graph_fields'])
    assert {k:v for k,v in af.items() if k != 'stable_ports'} == {k:v for k,v in bf.items() if k != 'stable_ports'}
    live = b['stable_fields']['live_stable_nodes']
    materialized = b['stable_fields']['materialized_stable_nodes']
    removed = b['stable_fields']['template_projected_nodes']
    assert live == a['stable_fields']['live_stable_nodes'] == materialized + removed
    saved = a['graph_owned_teardown_bytes'] - b['graph_owned_teardown_bytes']
    assert saved == af['stable_ports'] - bf['stable_ports']
    assert a['source_storage']['completed_owners']['restoration'] == b['source_storage']['completed_owners']['restoration']
    rows.append(dict(case=case, program=b['program_sha256'],
        graph_bytes_before=a['graph_owned_teardown_bytes'], graph_bytes_after=b['graph_owned_teardown_bytes'],
        graph_bytes_saved=saved, percent_saved=round(100*saved/a['graph_owned_teardown_bytes'], 3),
        logical_stable_facts=live, materialized_node_records=materialized, node_records_removed=removed,
        process_peak_before=a['execution_and_takeover_peak_bytes'], process_peak_after=b['execution_and_takeover_peak_bytes'],
        same_final_state_lifecycle_and_restoration=True))
Path(sys.argv[2]).write_text(json.dumps(dict(
    scope='actual standalone Cell runtime; opt-in template field projection; not native egglog or speed results',
    limitation='logical facts and Cell identities are unchanged; overlapping completion is unsupported; process peaks include Program and Executor',
    cases=rows), indent=2)+'\n')
