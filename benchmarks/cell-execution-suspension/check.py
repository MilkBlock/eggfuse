#!/usr/bin/env python3
"""Validate suspension ownership against the complete saved runtime executions."""
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
    new = ('rhs_context_suspends', 'rhs_context_resumes', 'rhs_suspend_private',
           'rhs_suspend_public', 'rhs_suspend_promotions', 'rhs_suspend_holds',
           'rhs_suspend_releases', 'rhs_suspend_invalidated')
    result = {'scope': 'standalone Cell CPU; not native egglog performance',
              'control_commit': 'b2fb26f9', 'control_binary_commit': '9345194d',
              'runtime_sha256': sha(root / 'runtime'), 'control_runtime_sha256': sha(prior / 'runtime'),
              'limits': 'Work and semantic regression only. These two workloads already have zero '
                        'later scalar dispatches; targeted boundary-result tests exercise suspension. '
                        'The production source-order driver still waits for a worker frontier.',
              'workloads': {}}
    step_keys = ('ordinal', 'ruleset', 'path', 'iterations', 'epoch',
                 'logical_matches', 'executed_bindings', 'changed')
    for case in ('sum', 'ray'):
        a, b = [read(base / case / 'report.json') for base in (prior, root)]
        assert a['status'] == b['status'] == 'complete'
        assert a['program_sha256'] == b['program_sha256']
        state = sha(root / case / 'state.json')
        assert state == sha(prior / case / 'state.json')
        assert [[s[k] for k in step_keys] for s in a['steps']] == [[s[k] for k in step_keys] for s in b['steps']]
        assert set(b['stats']) - set(a['stats']) == set(new)
        for key, value in a['stats'].items():
            assert value == b['stats'][key], (case, 'stats', key)
        for key in ('key_lookup_calls', 'fact_decode_calls', 'fact_decode_ports', 'maintenance',
                    'free_join', 'entry_schedule', 'known_results', 'neighbor_context', 'indexed_columns',
                    'repair_ports', 'multi_stage', 'cell_ownership', 'stable_ports', 'live_cells'):
            assert a[key] == b[key], (case, key)
        for group in ('stage_spine', 'query_workers'):
            for key, value in a[group]['stats'].items():
                after = b[group]['stats'][key]
                if group == 'query_workers' and key in ('worker_entries', 'worker_local_operations', 'worker_steps'):
                    assert len(value) == len(after) and sum(value) == sum(after), (case, key)
                elif not key.endswith('_seconds'):
                    assert value == after, (case, group, key)
        assert a['query_workers']['matched'] == b['query_workers']['matched']
        assert a['cell_execution']['runtime']['stats'] == b['cell_execution']['runtime']['stats']
        assert b['cell_execution']['runtime']['stats']['worker_segments'] == 0
        assert all(b['stats'][k] == 0 for k in new), 'no new suspension work without a dispatched suffix'
        assert b['cell_execution']['rhs_owner_bytes'] == a['cell_execution']['rhs_owner_bytes']
        result['workloads'][case] = {
            'runs': len(b['steps']), 'state_sha256': state, 'program_sha256': b['program_sha256'],
            'before_report_sha256': sha(prior / case / 'report.json'),
            'after_report_sha256': sha(root / case / 'report.json'),
            'exact_final_state_ordered_run_summaries_and_checked_work': True,
            'costs': {key: b['stats'][key] for key in new},
            'suspension': b['cell_execution']['suspension'],
            'ordinary_execution_header_bytes': b['cell_execution']['rhs_owner_bytes'],
            'entry_applications': (b['cell_ownership']['stats'] or {}).get('marker_entries', 0),
        }
    acceptance = read(root / 'semantic-acceptance.json')
    assert acceptance['status'] == 'pass'
    assert acceptance['input_sha256']['cpu_values'] == result['workloads']['sum']['state_sha256']
    result['native_sum_acceptance'] = {'status': 'pass', 'sha256': sha(root / 'semantic-acceptance.json')}
    log = root / 'integration-tests-final.log'
    text = log.read_text()
    assert 'test result: FAILED' not in text and 'test result: ok.' in text
    fixture = [json.loads(line.removeprefix('suspension ')) for line in text.splitlines()
               if line.startswith('suspension ')]
    assert {(r['prefix'], r['workers'], r['ownership']) for r in fixture} == {
        (prefix, workers, ownership) for prefix in ('', '(F x n)', '(set (Input x) (+ n 100))')
        for workers in (2, 4) for ownership in (False, True)}
    assert len(fixture) == 12
    for row in fixture:
        assert row['suspends'] == row['resumes'] > 0
        assert row['private'] + row['public'] == row['suspends']
        assert row['holds'] == row['releases']
        assert row['worker_operations'] > 0
    result['boundary_fixture'] = {'log_sha256': sha(log), 'samples': fixture,
        'scope': 'native checks and disabled-runtime Run-state equality; not timing'}
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    check(*map(Path, sys.argv[1:]))
