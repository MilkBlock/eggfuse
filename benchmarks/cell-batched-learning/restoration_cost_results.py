"""Summarize cause-tagged unsealing without attributing all repair to union."""
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
cases = []
for name in ('fact', 'loopfact', 'sum-bits', 'dot-product'):
    d = root/name
    before = json.loads((d/'candidate-stage-inherited-heap.json').read_text())
    after = json.loads((d/'candidate-restoration-audit-heap.json').read_text())
    assert before['program_sha256'] == after['program_sha256']
    assert before['final_state_sha256'] == after['final_state_sha256']
    assert before['source_storage']['fact_lifecycle'] == after['source_storage']['fact_lifecycle']
    owners = after['source_storage']['completed_owners']
    restore = owners['restoration']
    assert restore['scalar_provider']['events'] + restore['component_retirement']['events'] == after['completion_work']['shared_owner_frames_restored']
    assert restore['representation']['events'] == owners['representation_fallbacks']
    cases.append(dict(case=name, program=after['program_sha256'], restoration=restore,
                      exact_lifecycle_trace_equal=True, final_state_equal=True))
Path(sys.argv[2]).write_text(json.dumps(dict(
    scope='actual standalone Cell runtime; completed-source restoration array capacities, not allocation peaks or timings',
    cases=cases),indent=2)+'\n')
