"""Compare atomic constructor completion against the explicit-history seed."""
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
rows = []
for name in ('fact', 'loopfact', 'sum-bits', 'dot-product'):
    directory = root / name
    before = json.loads((directory / 'candidate-explicit-history-heap.json').read_text())
    after = json.loads((directory / 'candidate-atomic-heap.json').read_text())
    assert before['program_sha256'] == after['program_sha256']
    assert before['final_state_sha256'] == after['final_state_sha256']
    def lifecycle(data):
        # Storage placement changes iteration order; compare by logical identity.
        return {frame['cell']: {k: v for k, v in frame.items()
                if k not in ('completed', 'completed_storage')}
                for frame in data['source_storage']['fact_lifecycle']['frames']}
    assert lifecycle(before) == lifecycle(after)
    rows.append(dict(case=name,
        graph_bytes_before=before['graph_owned_teardown_bytes'],
        graph_bytes_after=after['graph_owned_teardown_bytes'],
        extra_eq_slots_elided=after['completion_work']['completed_symbolic_slots_elided']
            - before['completion_work']['completed_symbolic_slots_elided'],
        restoration=after['source_storage']['completed_owners']['restoration'],
        same_final_state_and_fact_lifecycle=True))
Path(sys.argv[2]).write_text(json.dumps(dict(
    scope='actual standalone Cell runtime; final Graph-owned heap, not runtime timing or native egglog memory',
    cases=rows), indent=2) + '\n')
