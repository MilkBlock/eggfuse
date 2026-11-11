#!/usr/bin/env python3
"""Validate saved executions and charge only removed subscription reads."""
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
    result = {'control_commit': '9ac332c4', 'scope': 'standalone Cell CPU',
              'runtime_sha256': sha(root / 'runtime'), 'workloads': {},
              'limits': 'Saved complete executions, not a timing campaign. No new parallel work or '
                        'reverse-edge removal. Root reads omitted are release-build operations; '
                        'debug assertions validate that those Eq fields are canonical.'}
    keys = ('ordinal', 'ruleset', 'path', 'iterations', 'epoch', 'logical_matches', 'executed_bindings', 'changed')
    for case in ('sum', 'ray'):
        old, new = prior / case, root / case
        a, b = read(old / 'report.json'), read(new / 'report.json')
        assert a['status'] == b['status'] == 'complete'
        assert a['program_sha256'] == b['program_sha256']
        assert sha(old / 'state.json') == sha(new / 'state.json')
        assert [[s[k] for k in keys] for s in a['steps']] == [[s[k] for k in keys] for s in b['steps']]
        for key in ('stats', 'key_lookup_calls', 'sieve', 'free_join', 'entry_schedule', 'known_results',
                    'neighbor_context', 'indexed_columns', 'repair_ports'):
            assert a[key] == b[key], (case, key)
        x, y = a['maintenance']['stats'], b['maintenance']['stats']
        for key in x:
            if key != 'subscription_value_visits':
                assert x[key] == y[key], (case, key)
        for key in a['maintenance'].keys() - {'stats'}:
            assert a['maintenance'][key] == b['maintenance'][key], (case, key)
        assert y['canonical_subscription_calls'] > 0
        assert y['subscription_scalar_fields_skipped'] > 0
        assert y['subscription_root_reads_omitted'] > 0
        assert y['subscription_sets_replaced_in_place'] > 0
        assert x['subscription_value_visits'] - y['subscription_value_visits'] == y['subscription_scalar_fields_skipped']
        for key in a['publication'].keys() - {'parallel'}:
            assert a['publication'][key] == b['publication'][key], (case, key)
        # Thread placement, capacity and timings are not deterministic work.
        for group in ('stats', 'residual_expansion'):
            u, v = a['query_workers'][group], b['query_workers'][group]
            if group == 'residual_expansion':
                u, v = u['stats'], v['stats']
            for key, count in u.items():
                if isinstance(count, int) and not any(s in key for s in ('capacity', 'bytes', 'growth', 'allocation')):
                    assert v[key] == count, (case, key)
        result['workloads'][case] = {
            'runs': len(b['steps']), 'program_sha256': b['program_sha256'],
            'state_sha256': sha(new / 'state.json'), 'before_report_sha256': sha(old / 'report.json'),
            'after_report_sha256': sha(new / 'report.json'), 'before': x, 'after': y,
            'same_state_ordered_runs_graph_queries_reverse_edges_and_publication': True,
        }
    accepted = read(root / 'semantic-acceptance.json')
    assert accepted['status'] == 'pass'
    assert accepted['input_sha256']['cpu_values'] == sha(root / 'sum/state.json')
    result['native_sum_acceptance'] = {'status': 'pass', 'sha256': sha(root / 'semantic-acceptance.json')}
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v['after'] for k, v in result['workloads'].items()}, indent=2))


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    check(*map(Path, sys.argv[1:]))
