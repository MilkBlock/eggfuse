#!/usr/bin/env python3
"""Verify scalar write-owner admission using saved runtime work and semantics."""
import hashlib
import json
from pathlib import Path
import runpy
import sys


def read(path):
    return json.loads(path.read_text())


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def work(report):
    execution = report['cell_execution']['runtime']['stats']
    return {
        'writes': {k: v for k, v in execution['writes'].items() if not k.endswith('_ns')},
        'key_lookup_calls': report['key_lookup_calls'],
        'scheduler': {k: v for k, v in execution['scheduler'].items() if not k.endswith('_ns')},
        'registry': {k: v for k, v in report['stats'].items() if k.startswith('unit_registry_')},
    }


def collect(control, candidate):
    keys = runpy.run_path(str(Path(__file__).parents[1] / 'raytrace-parallel/measure.py'))['KEYS']
    effects = ('constructor_requests', 'constructor_reused', 'logical_facts_created',
               'function_updates', 'union_requests', 'unions', 'bindings')
    result = {
        'scope': 'actual standalone Cell CPU; work counts, not native runtime performance',
        'control_commit': '772b98f5',
        'control_runtime_sha256': sha(control / 'candidate-runtime'),
        'candidate_runtime_sha256': sha(candidate / 'candidate-runtime'),
        'new_performance_measurement': False,
        'capacity_accounting': 'cumulative payload capacity, not peak memory or total allocation bytes',
        'workloads': {},
    }
    for case in ('sum', 'ray'):
        a, b = (read(root / f'candidate-{case}/report.json') for root in (control, candidate))
        assert a['status'] == b['status'] == 'complete'
        assert a['program_sha256'] == b['program_sha256']
        state = sha(candidate / f'candidate-{case}/state.json')
        assert state == sha(control / f'candidate-{case}/state.json')
        runs = [[step[k] for k in keys] for step in a['steps']]
        assert runs == [[step[k] for k in keys] for step in b['steps']]
        assert all(a['stats'][k] == b['stats'][k] for k in effects)
        old, new = work(a), work(b)
        counts = new['writes']
        # Every pre-existing non-timing write metric is comparable, including
        # payload capacity, final writes, superseded improvements and reuse.
        assert all(counts[k] == value for k, value in old['writes'].items())
        assert counts['owner_pool_calls'] == counts['batches']
        assert counts['owner_candidates'] == counts['admission_probes'] == counts['candidates']
        assert counts['direct_batches'] == counts['batches']
        assert counts['worker_key_rows'] == counts['candidates']
        assert counts['owner_sort_rows'] == 2 * counts['candidates']
        assert counts['new_rows'] <= counts['new_key_rechecks'] <= counts['candidates']
        assert counts['invalidated'] + counts['row_writes'] == counts['candidates']
        result['workloads'][case] = {
            'program_sha256': b['program_sha256'], 'state_sha256': state, 'runs': len(runs),
            'exact_final_state_and_run_summaries': True, 'logical_effects_equal': True,
            'work': {'control': old, 'candidate': new},
            'extra_global_query_lookups': new['key_lookup_calls'] - old['key_lookup_calls'],
            'extra_write_directory_probes': counts['new_key_rechecks'],
        }
        initial = candidate / 'initial' / f'candidate-{case}'
        first = read(initial / 'report.json')
        assert sha(initial / 'state.json') == state
        assert runs == [[step[k] for k in keys] for step in first['steps']]
        result['workloads'][case]['initial_work_only'] = work(first)
    assert result['workloads']['ray']['work']['candidate']['writes']['worker_key_rows'] > 0
    result['initial_runtime_sha256'] = sha(candidate / 'initial/candidate-runtime')
    proof = read(candidate / 'semantic-acceptance.json')
    assert proof['status'] == 'pass'
    assert proof['input_sha256']['cpu_values'] == result['workloads']['sum']['state_sha256']
    result['native_sum_semantic_acceptance'] = {
        'status': 'pass', 'sha256': sha(candidate / 'semantic-acceptance.json'),
    }
    return result


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    result = collect(Path(sys.argv[1]), Path(sys.argv[2]))
    Path(sys.argv[3]).write_text(json.dumps(result, indent=2) + '\n')
    print('Write-owner work, exact states, ordered Run summaries and sum acceptance verified')
