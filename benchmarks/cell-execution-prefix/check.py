#!/usr/bin/env python3
"""Compare completed executions and charge fused Cell preparation work."""
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
    result = {
        'scope': 'standalone Cell CPU', 'control_commit': '4ba83913',
        'control_tag': 'cell-execution-refactor-base', 'runtime_sha256': sha(root / 'runtime'),
        'limits': 'Complete work/semantic runs, not throughput or utilization evidence. '
                  'Prepared work includes losing candidates; only consumed operations '
                  'remove serial RHS execution. Capacity bytes exclude allocator overhead.',
        'workloads': {},
    }
    step_keys = ('ordinal', 'ruleset', 'path', 'iterations', 'epoch',
                 'logical_matches', 'executed_bindings', 'changed')
    for case in ('sum', 'ray'):
        old, new = prior / case, root / case
        a, b = read(old / 'report.json'), read(new / 'report.json')
        assert a['status'] == b['status'] == 'complete'
        assert a['program_sha256'] == b['program_sha256']
        assert sha(old / 'state.json') == sha(new / 'state.json')
        assert [[s[k] for k in step_keys] for s in a['steps']] == [[s[k] for k in step_keys] for s in b['steps']]
        for key in ('key_lookup_calls', 'maintenance', 'free_join', 'entry_schedule',
                    'known_results', 'neighbor_context', 'indexed_columns', 'repair_ports'):
            assert a[key] == b[key], (case, key)
        for key, value in a['stats'].items():
            assert b['stats'][key] == value, (case, 'stats', key, value, b['stats'][key])
        w = b['query_workers']['stats']
        prepared = w['execution']['operations']
        worker = sum(w['worker_local_operations'])
        consumed = b['stats']['prepared_rhs_operations']
        assert 0 <= consumed <= prepared and 0 <= worker <= prepared
        if case == 'ray':
            assert consumed > 0 and worker > 0
        result['workloads'][case] = {
            'runs': len(b['steps']), 'state_sha256': sha(new / 'state.json'),
            'program_sha256': b['program_sha256'],
            'before_report_sha256': sha(old / 'report.json'),
            'after_report_sha256': sha(new / 'report.json'),
            'same_state_ordered_runs_and_graph_query_maintenance_work': True,
            'plan': b['cell_execution'], 'preparation': w['execution'],
            'worker_local_operations': worker,
            'inline_local_operations': prepared - worker,
            'serial_rhs_operations_removed': consumed,
            'prepared_operations_not_consumed': prepared - consumed,
        }
    accepted = read(root / 'semantic-acceptance.json')
    assert accepted['status'] == 'pass'
    assert accepted['input_sha256']['cpu_values'] == sha(root / 'sum/state.json')
    result['native_sum_acceptance'] = {'status': 'pass', 'sha256': sha(root / 'semantic-acceptance.json')}
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: {n: v[n] for n in ('runs', 'worker_local_operations',
                     'serial_rhs_operations_removed', 'prepared_operations_not_consumed')}
                     for k, v in result['workloads'].items()}, indent=2))


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    check(*map(Path, sys.argv[1:]))
