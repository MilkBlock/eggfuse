#!/usr/bin/env python3
"""Check one completed sum-bits run against the preceding owned-prefix build."""
import hashlib
import json
from pathlib import Path
import sys


def read(path):
    return json.loads(path.read_text())


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def check(root, prior, output):
    a, b = (read(p / 'sum/report.json') for p in (prior, root))
    assert a['status'] == b['status'] == 'complete'
    assert a['program_sha256'] == b['program_sha256']
    assert sha(prior / 'sum/state.json') == sha(root / 'sum/state.json')
    fields = ('ordinal', 'ruleset', 'path', 'iterations', 'epoch',
              'logical_matches', 'executed_bindings', 'changed')
    assert [[s[k] for k in fields] for s in a['steps']] == [[s[k] for k in fields] for s in b['steps']]
    for key in ('key_lookup_calls', 'maintenance', 'free_join', 'entry_schedule',
                'known_results', 'neighbor_context', 'indexed_columns', 'repair_ports'):
        assert a[key] == b[key], key
    for key, value in a['stats'].items():
        assert b['stats'][key] == value, ('stats', key, value, b['stats'][key])
    accepted = read(root / 'semantic-acceptance.json')
    assert accepted['status'] == 'pass'
    assert accepted['input_sha256']['cpu_values'] == sha(root / 'sum/state.json')
    result = {
        'scope': 'standalone Cell CPU', 'control_commit': '2ed50ac1',
        'runtime_sha256': sha(root / 'runtime'),
        'program_sha256': b['program_sha256'],
        'state_sha256': sha(root / 'sum/state.json'),
        'before_report_sha256': sha(prior / 'sum/report.json'),
        'after_report_sha256': sha(root / 'sum/report.json'),
        'runs': len(b['steps']),
        'same_state_ordered_runs_and_prior_work_counters': True,
        'completion_storage': {k: v for k, v in b['stats'].items()
                               if k.startswith(('completion_frame_', 'completion_promoted_'))},
        'native_sum_acceptance': {'status': 'pass', 'sha256': sha(root / 'semantic-acceptance.json')},
        'limits': 'Work/semantic check only, no speed comparison. Promoted result slots '
                  'count the removed second insertion on a first-miss promotion. '
                  'Growth bytes are added capacity, not allocation traffic or peak memory.',
    }
    assert result['completion_storage']['completion_promoted_result_slots'] > 0
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result['completion_storage'], indent=2))


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    check(*map(Path, sys.argv[1:]))
