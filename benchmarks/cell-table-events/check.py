#!/usr/bin/env python3
"""Validate table-driven conditions against the preceding actual CPU execution."""
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
    publication = report['publication']['parallel']
    conditions = report['sieve']['publication']['stats']
    return {
        'table_publication': {k: v for k, v in publication.items()
                              if not k.endswith('_seconds') and not isinstance(v, list)},
        'conditions': {k: v for k, v in conditions.items()
                       if not k.endswith('_seconds') and not isinstance(v, list)},
        'sieve_total': report['sieve']['stats'],
        'key_lookup_calls': report['key_lookup_calls'],
    }


def collect(control, candidate):
    keys = runpy.run_path(str(Path(__file__).parents[1] / 'raytrace-parallel/measure.py'))['KEYS']
    effects = ('constructor_requests', 'constructor_reused', 'logical_facts_created',
               'function_updates', 'union_requests', 'unions', 'bindings')
    result = {
        'scope': 'actual standalone Cell CPU, work and semantic checks; not a timing campaign or native egglog performance',
        'control_commit': '1bb73355', 'control_runtime_commit': '79e6fe0f',
        'control_runtime_sha256': sha(control / 'candidate-runtime'),
        'candidate_runtime_sha256': sha(candidate / 'candidate-runtime'),
        'limits': 'Potential and empty nodes include speculative preparation. Early nodes require unfinished table computation after condition completion; early_work_nodes excludes empty propagation. Capacity is cumulative payload capacity, not allocation traffic or peak live memory. Group capacity reuses the existing plan buffers; only group_header_bytes and capacity growth are separate charges.',
        'workloads': {},
    }
    for case in ('sum', 'ray'):
        a, b = (read(root / f'candidate-{case}/report.json') for root in (control, candidate))
        assert a['status'] == b['status'] == 'complete'
        assert a['program_sha256'] == b['program_sha256']
        state = sha(candidate / f'candidate-{case}/state.json')
        assert state == sha(control / f'candidate-{case}/state.json')
        runs = [[s[k] for k in keys] for s in a['steps']]
        assert runs == [[s[k] for k in keys] for s in b['steps']]
        assert all(a['stats'][k] == b['stats'][k] for k in effects)
        assert a['sieve']['stats'] == b['sieve']['stats']
        assert a['key_lookup_calls'] == b['key_lookup_calls']
        for key in ('headers', 'column_rows', 'range_rows', 'neighbor_rows', 'header_only', 'row_reads'):
            assert a['publication'][key] == b['publication'][key], key
        old, new = work(a), work(b)
        event = new['conditions']['table_events']
        assert event['potential_nodes'] == event['completed_nodes']
        assert event['failed_batches'] == event['discarded_nodes'] == 0
        assert event['early_work_nodes'] <= event['early_nodes'] <= event['completed_nodes']
        assert event['empty_nodes'] <= event['completed_nodes']
        assert event['batches'] == new['table_publication']['condition_batches']
        assert old['table_publication']['pool_calls'] == new['table_publication']['pool_calls']
        for key in ('pending_group_rows', 'pending_support_keys', 'pending_tasks'):
            assert b['sieve']['publication'][key] == 0
        result['workloads'][case] = {
            'program_sha256': b['program_sha256'], 'state_sha256': state, 'runs': len(runs),
            'schedule_sha256': hashlib.sha256(json.dumps(runs, separators=(',', ':')).encode()).hexdigest(),
            'exact_final_state_and_run_summaries': True, 'logical_effects_and_sieve_totals_equal': True,
            'work': {'control': old, 'candidate': new},
            'separate_condition_pool_calls_removed': old['conditions']['pool_calls'] - new['conditions']['pool_calls'],
        }
    event = result['workloads']['ray']['work']['candidate']['conditions']['table_events']
    assert event['early_work_nodes'] > 0 and event['change_handoff_rows_avoided'] > 0
    assert result['workloads']['ray']['separate_condition_pool_calls_removed'] > 0
    proof = read(candidate / 'semantic-acceptance.json')
    assert proof['status'] == 'pass'
    assert proof['input_sha256']['cpu_values'] == result['workloads']['sum']['state_sha256']
    result['native_sum_acceptance'] = {'status': 'pass', 'sha256': sha(candidate / 'semantic-acceptance.json')}
    result['initial_counter_version'] = {
        'scope': 'same execution logic before splitting reused group capacity from new header/growth costs; not timing',
        'runtime_sha256': sha(candidate / 'initial/candidate-runtime'),
        'ray_event_counts': work(read(candidate / 'initial/candidate-ray/report.json'))['conditions']['table_events'],
    }
    return result


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    Path(sys.argv[3]).write_text(json.dumps(collect(Path(sys.argv[1]), Path(sys.argv[2])), indent=2) + '\n')
    print('Table/condition takeover, exact states, Run summaries and native sum contract verified')
