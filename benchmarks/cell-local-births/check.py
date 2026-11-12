#!/usr/bin/env python3
"""Verify fresh local Cell construction against saved source-ordered execution."""
import hashlib
import json
from pathlib import Path
import sys


def read(path):
    return json.loads(path.read_text())


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def work(value):
    """Ignore timings and worker assignment, retaining total actual operations."""
    if not isinstance(value, dict):
        return value
    return {k: sum(v) if isinstance(v, list) and 'worker_' in k else work(v)
            for k, v in value.items() if not k.endswith(('_seconds', '_ns'))}


def check(root, prior, output):
    result = {'scope': 'standalone Cell CPU; work and semantics, not a timing campaign',
              'control_commit': '4088086e', 'runtime_sha256': sha(root / 'runtime'),
              'control_runtime_sha256': sha(prior / 'runtime'), 'workloads': {}}
    fields = ('ordinal', 'ruleset', 'path', 'iterations', 'epoch',
              'logical_matches', 'executed_bindings', 'changed')
    for case in ('sum', 'ray'):
        a, b = [read(base / case / 'report.json') for base in (prior, root)]
        assert a['status'] == b['status'] == 'complete'
        assert a['program_sha256'] == b['program_sha256']
        state = sha(root / case / 'state.json')
        assert state == sha(prior / case / 'state.json')
        assert [[s[k] for k in fields] for s in a['steps']] == [[s[k] for k in fields] for s in b['steps']]
        for key in ('stats', 'maintenance', 'free_join', 'entry_schedule', 'known_results',
                    'neighbor_context', 'indexed_columns', 'repair_ports', 'multi_stage',
                    'cell_ownership', 'live_cells', 'fact_decode_calls', 'stage_spine', 'query_workers'):
            assert work(a[key]) == work(b[key]), (case, key)
        old_run, new_run = [r['cell_execution']['runtime']['stats'] for r in (a, b)]
        for key, value in old_run.items():
            if key != 'boundaries':
                assert value == new_run[key], (case, key)
        assert old_run['boundaries'][1:] == new_run['boundaries'][1:]
        removed_boundaries = old_run['boundaries'][0] - new_run['boundaries'][0]
        counts = new_run['births']
        assert counts['local_births'] == counts['committed_rows'] > 0
        assert counts['worker_operations'] == counts['local_births'] + counts['local_reuses']
        assert a['key_lookup_calls'] - b['key_lookup_calls'] == counts['worker_operations']
        assert removed_boundaries >= counts['worker_operations']
        assert counts['worker_batches'] > 0
        assert counts['invalidated'] == counts['missing_operands'] == 0
        plan = b['cell_execution']['local_construction']
        assert plan['schema'] == 'cell-local-births/v1'
        assert plan['independent_scheduling'] is False
        assert b['cell_execution']['rhs_owner_bytes'] - a['cell_execution']['rhs_owner_bytes'] == plan['window_bytes']
        assert a['query_workers']['instance_header_bytes'] == b['query_workers']['instance_header_bytes']
        delta = read(root / f'{case}-work.json')
        result['workloads'][case] = {
            'program_sha256': b['program_sha256'], 'state_sha256': state, 'runs': len(b['steps']),
            'exact_final_state_and_ordered_run_summaries': True,
            'graph_effects_queries_repair_and_publication_work_unchanged': True,
            'total_lookup_calls': [a['key_lookup_calls'], b['key_lookup_calls']],
            'source_constructor_boundaries': [old_run['boundaries'][0], new_run['boundaries'][0]],
            'removed_lookup_calls': counts['worker_operations'],
            'local_construction': counts, 'compiled_local_plan': plan,
            'useful_constructors_per_worker_batch': counts['worker_operations'] / counts['worker_batches'],
            'instance_header_bytes': b['query_workers']['instance_header_bytes'],
            'execution_header_bytes': [a['cell_execution']['rhs_owner_bytes'], b['cell_execution']['rhs_owner_bytes']],
            'compiled_execution_bytes': [a['cell_execution']['compiled_payload_bytes'], b['cell_execution']['compiled_payload_bytes']],
            'net_saved_uncalibrated_operations': delta['net_saved_operations'],
            'work_ledger_sha256': sha(root / f'{case}-work.json'),
        }
    acceptance = read(root / 'semantic-acceptance.json')
    assert acceptance['status'] == 'pass'
    assert acceptance['input_sha256']['cpu_values'] == result['workloads']['sum']['state_sha256']
    result['native_sum_acceptance'] = {'status': 'pass', 'sha256': sha(root / 'semantic-acceptance.json')}
    output.write_text(json.dumps(result, indent=2) + '\n')
    print('same effects, final states and ordered Runs; local construction and added costs accounted')


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    check(*map(Path, sys.argv[1:]))
