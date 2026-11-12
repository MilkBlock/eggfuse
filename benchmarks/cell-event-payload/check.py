#!/usr/bin/env python3
"""Check task-local query accounting without changing Cell execution evidence."""
import hashlib
import json
from pathlib import Path
import runpy
import sys


def read(path):
    return json.loads(path.read_text())


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def collect(control, candidate):
    base = runpy.run_path(str(Path(__file__).parents[1] / 'raytrace-parallel/measure.py'))
    effects = ('constructor_requests', 'constructor_reused', 'logical_facts_created',
               'function_updates', 'union_requests', 'unions', 'bindings')
    result = {'scope': 'actual standalone Cell CPU work; not timing or native egglog performance',
              'control_commit': 'f48eb140', 'control_runtime_sha256': sha(control / 'candidate-runtime'),
              'candidate_runtime_sha256': sha(candidate / 'candidate-runtime'), 'workloads': {}}
    assert result['candidate_runtime_sha256'] == read(candidate / 'manifest.json')['runtime_sha256']
    for case in ('sum', 'ray'):
        a, b = (read(root / f'candidate-{case}/report.json') for root in (control, candidate))
        state = sha(control / f'candidate-{case}/state.json')
        runs = [[s[k] for k in base['KEYS']] for s in a['steps']]
        assert a['status'] == b['status'] == 'complete'
        assert a['program_sha256'] == b['program_sha256']
        assert state == sha(candidate / f'candidate-{case}/state.json')
        assert runs == [[s[k] for k in base['KEYS']] for s in b['steps']]
        assert all(a['stats'][k] == b['stats'][k] for k in effects)
        assert a['key_lookup_calls'] == b['key_lookup_calls']
        assert a['sieve']['stats'] == b['sieve']['stats']
        assert a['stage_spine']['iterative_bake'] == b['stage_spine']['iterative_bake']
        old, new = a['query_workers'], b['query_workers']
        # Keep every old report field. Scheduling can change frame capacities,
        # worker attribution, event waves and sorting comparison counts.
        assert old['stats'].keys() == new['stats'].keys()
        for k in ('entries', 'answers', 'steps', 'point_reads', 'result_writes', 'guards',
                  'guard_rejections', 'owner_rejections', 'chunks', 'frame_cache_borrows',
                  'entry_headers', 'coverage_range_rows', 'coverage_admitted_entries',
                  'coverage_rules', 'coverage_complete_rules', 'coverage_cursor_resolutions',
                  'coverage_empty_rules', 'entry_range_chunks', 'entry_range_batches'):
            assert old['stats'][k] == new['stats'][k], k
        assert old['stats']['execution'] == new['stats']['execution']
        assert old['stats']['constructors'] == new['stats']['constructors']
        for k in ('entries', 'answers', 'input_rows', 'point_reads', 'column_prepares',
                  'expansion_rows', 'filter_probes', 'filter_rejected', 'partitioned_entries',
                  'partitioned_admitted', 'partitioned_answers', 'merge_tasks', 'run_pool_calls'):
            assert old['residual_expansion']['stats'][k] == new['residual_expansion']['stats'][k], k
        assert new['query_task_counter_bytes'] < new['query_executor_counter_bytes']
        assert new['residual_expansion']['task_counter_bytes'] < new['residual_expansion']['executor_counter_bytes']
        assert new['stats']['event_bytes'] < old['stats']['event_bytes']
        def costs(q):
            return {k: q['stats'][k] for k in ('chunks', 'event_bytes', 'entry_range_batches',
                    'coverage_event_heap_bytes', 'range_answer_span_heap_bytes',
                    'answer_buffer_allocations', 'output_buffer_capacity')}
        result['workloads'][case] = {
            'program_sha256': b['program_sha256'], 'state_sha256': state, 'runs': len(runs),
            'schedule_sha256': hashlib.sha256(json.dumps(runs, separators=(',', ':')).encode()).hexdigest(),
            'exact_final_state_runs_effects_and_query_accounting': True,
            'logical_effects': {k: b['stats'][k] for k in effects},
            'work': {'control': costs(old), 'candidate': costs(new)},
            'fixed_layout_bytes': {k: new[k] for k in ('completion_event_bytes',
                'query_task_counter_bytes', 'query_executor_counter_bytes')},
            'residual_counter_bytes': {k: new['residual_expansion'][k] for k in
                ('task_counter_bytes', 'executor_counter_bytes')},
        }
    proof = read(candidate / 'semantic-acceptance.json')
    assert proof['status'] == 'pass'
    assert proof['input_sha256']['cpu_values'] == result['workloads']['sum']['state_sha256']
    result['native_sum_acceptance'] = {'status': 'pass', 'sha256': sha(candidate / 'semantic-acceptance.json')}
    return result


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    Path(sys.argv[3]).write_text(json.dumps(collect(Path(sys.argv[1]), Path(sys.argv[2])), indent=2) + '\n')
    print('Task payload, query accounting, exact Runs and native sum contract verified')
