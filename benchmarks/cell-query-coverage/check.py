#!/usr/bin/env python3
"""Validate deferred mixed-Cell coverage against the preceding CPU execution."""
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
    def scalars(values):
        return {k: v for k, v in values.items() if isinstance(v, (int, bool)) and not k.endswith('_ns')}
    return {'queries': scalars(report['query_workers']['stats']),
            'expansions': scalars(report['query_workers']['residual_expansion']['stats']),
            'expansion_plan_capacity_bytes': report['query_workers']['residual_expansion']['plan_capacity_bytes']}


def collect(control, candidate):
    keys = runpy.run_path(str(Path(__file__).parents[1] / 'raytrace-parallel/measure.py'))['KEYS']
    effects = ('constructor_requests', 'constructor_reused', 'logical_facts_created',
               'function_updates', 'union_requests', 'unions', 'bindings')
    result = {
        'scope': 'actual standalone Cell CPU work and semantic checks; not timing or native egglog performance',
        'control_commit': '1cd06be0',
        'control_runtime_sha256': sha(control / 'candidate-runtime'),
        'candidate_runtime_sha256': sha(candidate / 'candidate-runtime'),
        'limits': 'Filters move to workers; the necessary checks remain. Coverage is resolved per rule before winner selection. Source Cursor writes, extra column activation, rejected range tasks and event payload are charged. Cumulative capacity is not allocated bytes or peak memory. This does not prove the preceding timing regression is fixed.',
        'workloads': {},
    }
    manifest = read(candidate / 'manifest.json')
    assert result['candidate_runtime_sha256'] == manifest['runtime_sha256']
    for case in ('sum', 'ray'):
        a, b = (read(root / f'candidate-{case}/report.json') for root in (control, candidate))
        assert a['status'] == b['status'] == 'complete'
        assert a['program_sha256'] == b['program_sha256']
        state = sha(control / f'candidate-{case}/state.json')
        assert state == sha(candidate / f'candidate-{case}/state.json')
        runs = [[s[k] for k in keys] for s in a['steps']]
        assert runs == [[s[k] for k in keys] for s in b['steps']]
        assert all(a['stats'][k] == b['stats'][k] for k in effects)
        assert a['sieve']['stats'] == b['sieve']['stats']
        assert a['key_lookup_calls'] == b['key_lookup_calls']
        assert a['stage_spine']['iterative_bake'] == b['stage_spine']['iterative_bake']
        for k in ('entries', 'answers', 'steps', 'point_reads', 'result_writes', 'guards', 'guard_rejections', 'owner_rejections'):
            assert a['query_workers']['stats'][k] == b['query_workers']['stats'][k], k
        for k in ('partitioned_entries', 'partitioned_admitted', 'partitioned_answers',
                  'entries', 'answers', 'point_reads', 'expansion_rows'):
            assert a['query_workers']['residual_expansion']['stats'][k] == b['query_workers']['residual_expansion']['stats'][k], k
        for k in ('fallback_by_rule', 'fallback_pivots', 'routed_matcher_seeds', 'routed_spine_seeds',
                  'mixed_routed_queries', 'uncovered_queries', 'completed_steps', 'sealed_partial_origins'):
            assert a['stage_spine']['stats'][k] == b['stage_spine']['stats'][k], k
        old, new = work(a), work(b)
        q, e = new['queries'], new['expansions']
        assert q['coverage_rules'] > 0
        assert q['coverage_range_rows'] >= q['coverage_admitted_entries'] > 0
        assert q['selected_range_entries'] + q['coverage_admitted_entries'] == e['partitioned_entries']
        assert old['queries']['selected_range_entries'] - q['selected_range_entries'] == q['coverage_admitted_entries']
        assert q['entry_range_row_borrows'] == q['entry_range_rows']
        assert e['queued_row_owners'] + q['entry_range_rows'] == e['input_rows']
        assert q['frame_cache_borrows'] == q['chunks']
        assert q['coverage_empty_rules'] > 0
        attempts = {}
        for name in ('uncoalesced', 'raw-pool-weight'):
            root = candidate / name
            previous = read(root / f'candidate-{case}/report.json')
            assert previous['status'] == 'complete'
            assert previous['program_sha256'] == b['program_sha256']
            assert sha(root / f'candidate-{case}/state.json') == state
            assert [[s[k] for k in keys] for s in previous['steps']] == runs
            assert all(previous['stats'][k] == a['stats'][k] for k in effects)
            assert previous['sieve']['stats'] == a['sieve']['stats']
            assert previous['key_lookup_calls'] == a['key_lookup_calls']
            binary_hash = sha(root / 'candidate-runtime')
            assert binary_hash == read(root / 'manifest.json')['runtime_sha256']
            attempts[name] = {'runtime_sha256': binary_hash, 'work': work(previous),
                              'exact_final_state_runs_effects_and_sieve': True}
        result['workloads'][case] = {
            'program_sha256': b['program_sha256'], 'state_sha256': state, 'runs': len(runs),
            'schedule_sha256': hashlib.sha256(json.dumps(runs, separators=(',', ':')).encode()).hexdigest(),
            'exact_final_state_and_run_summaries': True,
            'logical_effects_query_steps_sieve_and_coverage_equal': True,
            'key_lookup_calls': b['key_lookup_calls'],
            'work': {'control': old, 'candidate': new},
            'earlier_work_runs': attempts,
        }
    failed = candidate / 'initial'
    assert 'Entry coverage precedes residual winner selection' in (failed / 'candidate-sum.log').read_text()
    assert not (failed / 'candidate-sum/report.json').exists()
    result['initial_failure'] = {'runtime_sha256': sha(failed / 'candidate-runtime'),
        'log_sha256': sha(failed / 'candidate-sum.log'),
        'reason': 'A coarse nonempty Entry admission produced no remaining range task; coverage was not resolved before winner selection. Fixed before accepted exports.'}
    proof = read(candidate / 'semantic-acceptance.json')
    assert proof['status'] == 'pass'
    assert proof['input_sha256']['cpu_values'] == result['workloads']['sum']['state_sha256']
    result['native_sum_acceptance'] = {'status': 'pass', 'sha256': sha(candidate / 'semantic-acceptance.json')}
    return result


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    Path(sys.argv[3]).write_text(json.dumps(collect(Path(sys.argv[1]), Path(sys.argv[2])), indent=2) + '\n')
    print('Deferred coverage, exact states, Run summaries and native sum contract verified')
