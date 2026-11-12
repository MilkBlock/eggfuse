#!/usr/bin/env python3
"""Check in-place condition owners against the preceding CPU execution."""
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


def counters(values):
    return {k: v for k, v in values.items()
            if not k.endswith('_seconds') and not isinstance(v, (list, dict))}


def collect(control, candidate):
    keys = runpy.run_path(str(Path(__file__).parents[1] / 'raytrace-parallel/measure.py'))['KEYS']
    effects = ('constructor_requests', 'constructor_reused', 'logical_facts_created',
               'function_updates', 'union_requests', 'unions', 'bindings')
    manifest = read(candidate / 'manifest.json')
    result = {
        'scope': 'actual standalone Cell CPU; work and semantic checks, not timing or native egglog performance',
        'control_commit': '4d42d965',
        'control_runtime_sha256': sha(control / 'candidate-runtime'),
        'candidate_runtime_sha256': sha(candidate / 'candidate-runtime'),
        'limits': 'Potential nodes and readiness edges remain. Empty nodes already ran inline in the control. Borrow partitioning adds sorting and handles. Header bytes are cumulative payload capacity, not allocator traffic, peak live memory or elapsed time. OnceLock<Finished> reserves its maximum payload for empty nodes too.',
        'workloads': {},
    }
    assert result['candidate_runtime_sha256'] == manifest['runtime_sha256']
    for case in ('sum', 'ray'):
        a, b = (read(root / f'candidate-{case}/report.json') for root in (control, candidate))
        assert a['status'] == b['status'] == 'complete'
        assert a['program_sha256'] == b['program_sha256']
        state = sha(candidate / f'candidate-{case}/state.json')
        assert state == sha(control / f'candidate-{case}/state.json')
        runs = [[s[k] for k in keys] for s in a['steps']]
        assert runs == [[s[k] for k in keys] for s in b['steps']]
        assert all(a['stats'][k] == b['stats'][k] for k in effects)
        assert a['sieve']['stats'] == b['sieve']['stats']  # Includes every per-rule counter.
        assert a['key_lookup_calls'] == b['key_lookup_calls']
        for key in ('headers', 'column_rows', 'range_rows', 'neighbor_rows', 'header_only', 'row_reads'):
            assert a['publication'][key] == b['publication'][key], key
        assert counters(a['publication']['parallel']) == counters(b['publication']['parallel'])
        old, new = (doc['sieve']['publication']['stats'] for doc in (a, b))
        for key, value in counters(old).items():
            if key != 'event_header_bytes':
                assert value == new[key], key
        prior, event = old['table_events'], new['table_events']
        for key, value in prior.items():
            if key not in ('early_nodes', 'early_work_nodes', 'header_bytes'):
                assert value == event[key], key
        assert event['potential_nodes'] == event['completed_nodes'] == event['summary_borrows']
        assert event['failed_batches'] == event['discarded_nodes'] == 0
        assert event['materialized_nodes'] + event['empty_nodes'] == event['completed_nodes']
        assert event['partition_steps'] == event['summary_borrows'] + event['unchanged_child_borrows']
        assert event['early_work_nodes'] <= event['early_nodes'] <= event['completed_nodes']
        assert prior['header_bytes'] - event['header_bytes'] == old['event_header_bytes'] - new['event_header_bytes']
        for key in ('pending_group_rows', 'pending_support_keys', 'pending_tasks'):
            assert b['sieve']['publication'][key] == 0
        result['workloads'][case] = {
            'program_sha256': b['program_sha256'], 'state_sha256': state, 'runs': len(runs),
            'schedule_sha256': hashlib.sha256(json.dumps(runs, separators=(',', ':')).encode()).hexdigest(),
            'exact_final_state_and_run_summaries': True,
            'logical_effects_and_all_sieve_counters_equal': True,
            'key_lookup_calls': b['key_lookup_calls'],
            'table_publication': counters(b['publication']['parallel']),
            'sieve_totals': counters(b['sieve']['stats']),
            'condition_work': {'control': counters(old), 'candidate': counters(new)},
            'table_events': {'control': prior, 'candidate': event},
            'header_capacity_bytes_removed': prior['header_bytes'] - event['header_bytes'],
            'derived_summary_moves_out_and_back_removed': 2 * event['summary_borrows'],
        }
    ray = result['workloads']['ray']
    assert ray['header_capacity_bytes_removed'] > 0
    assert ray['table_events']['candidate']['empty_nodes'] > 0
    assert ray['table_events']['candidate']['unchanged_child_borrows'] > 0
    proof = read(candidate / 'semantic-acceptance.json')
    assert proof['status'] == 'pass'
    assert proof['input_sha256']['cpu_values'] == result['workloads']['sum']['state_sha256']
    result['native_sum_acceptance'] = {'status': 'pass', 'sha256': sha(candidate / 'semantic-acceptance.json')}
    return result


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    Path(sys.argv[3]).write_text(json.dumps(collect(Path(sys.argv[1]), Path(sys.argv[2])), indent=2) + '\n')
    print('In-place conditions, exact states, Run summaries and native sum contract verified')
