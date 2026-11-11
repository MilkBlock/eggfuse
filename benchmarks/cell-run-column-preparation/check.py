#!/usr/bin/env python3
"""Compare saved complete executions; no performance run is launched."""
import hashlib
import json
from pathlib import Path
import sys


def read(p):
    return json.loads(p.read_text())


def sha(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def check(root, prior, output):
    result = {'control_commit': '10588f41', 'scope': 'standalone Cell CPU',
              'runtime_sha256': sha(root / 'runtime'), 'workloads': {},
              'limits': 'No throughput claim. Old prepare calls are reconstructed from unchanged activation calls; '
                        'the old binary has no dedicated prepare counter. Reuses count removed preparation '
                        'calls, not allocations or logical/committed mutations.'}
    keys = ('ordinal', 'ruleset', 'path', 'iterations', 'epoch', 'logical_matches', 'executed_bindings', 'changed')
    for name in ('sum', 'ray'):
        old, new = prior / ('parallel-' + name), root / name
        a, b = read(old / 'report.json'), read(new / 'report.json')
        assert a['status'] == b['status'] == 'complete'
        assert a['program_sha256'] == b['program_sha256']
        assert sha(old / 'state.json') == sha(new / 'state.json')
        assert [[s[k] for k in keys] for s in a['steps']] == [[s[k] for k in keys] for s in b['steps']]
        for k in ('stats', 'key_lookup_calls', 'sieve', 'free_join', 'entry_schedule', 'known_results', 'indexed_columns'):
            assert a[k] == b[k], k
        assert a['neighbor_context'] == b['neighbor_context']
        for k in a['publication'].keys() - {'parallel'}:
            assert a['publication'][k] == b['publication'][k], k
        x, y = (r['query_workers']['residual_expansion']['stats'] for r in (a, b))
        # Per-worker placement/timing may change; all scalar logical work stays.
        for k, v in x.items():
            if isinstance(v, int) and not k.endswith('capacity_bytes'):
                assert y[k] == v, (name, k, v, y[k])
        assert y['column_prepare_reuses'] > 0 and y['column_prepares'] > 0
        result['workloads'][name] = {
            'runs': len(b['steps']), 'program_sha256': b['program_sha256'],
            'state_sha256': sha(new / 'state.json'), 'before_report_sha256': sha(old / 'report.json'),
            'after_report_sha256': sha(new / 'report.json'),
            'same_state_ordered_runs_graph_queries_admission_filters_and_publication': True,
            'old_prepare_calls_reconstructed': y['column_prepares'] + y['column_prepare_reuses'],
            'prepare_calls': y['column_prepares'], 'reused_preparation': y['column_prepare_reuses'],
            'partitioned_entries': y['partitioned_entries'], 'partitioned_pivots': y['partitioned_pivots'],
        }
    a = read(root / 'semantic-acceptance.json')
    assert a['status'] == 'pass' and a['input_sha256']['cpu_values'] == sha(root / 'sum/state.json')
    result['native_sum_acceptance'] = {'status': 'pass', 'sha256': sha(root / 'semantic-acceptance.json')}
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result['workloads'], indent=2))


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    check(*map(Path, sys.argv[1:]))
