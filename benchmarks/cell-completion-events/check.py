#!/usr/bin/env python3
"""Check completion-event coverage, semantic evidence and all timing samples."""
import hashlib
import json
from pathlib import Path
import runpy
import statistics
import sys


def read(path):
    return json.loads(path.read_text())


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def work(report):
    query = report['query_workers']['stats']
    execution = report['cell_execution']['runtime']['stats']
    return {
        'queries': {k: v for k, v in query.items() if k.startswith('event_') or k in (
            'batches', 'chunks', 'entries', 'answers', 'point_reads',
            'completion_headers', 'completion_error_checks', 'entry_buffer_bytes')},
        'key_lookup_calls': report['key_lookup_calls'],
        'ready_rhs': execution['scheduler'],
        'constructors': execution['births'],
        'unit_registry': {k: v for k, v in report['stats'].items() if k.startswith('unit_registry_')},
        'residual_merge': {k: v for k, v in report['query_workers']['residual_expansion']['stats'].items()
                           if k.startswith('merge_') or k == 'order_comparisons'},
        'conditions': report['sieve']['publication']['stats'],
        'publication': report['publication'],
    }


def collect(root):
    keys = runpy.run_path(str(Path(__file__).parents[1] / 'raytrace-parallel/measure.py'))['KEYS']
    effects = ('constructor_requests', 'constructor_reused', 'logical_facts_created',
               'function_updates', 'union_requests', 'unions', 'bindings')
    result = {
        'scope': 'actual standalone Cell CPU, not native egglog performance',
        'control_commit': 'cf452ed6', 'control_runtime_commit': '8335929d',
        'candidate_commit': '2ae7b97e',
        'capacity_accounting': 'cumulative payload capacity; not complete allocator traffic or peak live memory',
        'remaining_boundaries': ['source-prefix shared effect adoption', 'source Run visibility/error fence',
                                 'table publication before condition observation', 'ordinary repair'],
        'preceding_campaign': {'file': 'preceding-results.json', 'candidate_commit': '4bc89976', 'overlap_counter_invalid': True},
        'workloads': {},
    }
    for case in ('sum', 'ray'):
        a, b = (read(root / f'{lane}-{case}/report.json') for lane in ('control', 'candidate'))
        assert a['status'] == b['status'] == 'complete'
        assert a['program_sha256'] == b['program_sha256']
        state = sha(root / f'candidate-{case}/state.json')
        assert state == sha(root / f'control-{case}/state.json')
        runs = [[s[k] for k in keys] for s in a['steps']]
        assert runs == [[s[k] for k in keys] for s in b['steps']]
        assert all(a['stats'][k] == b['stats'][k] for k in effects)
        assert a['key_lookup_calls'] == b['key_lookup_calls']
        assert b['query_workers']['overlap_measurement'] == 'unfinished-jobs-after-seal/v1'
        expected = {'state_sha256': state, 'schedule_sha256': hashlib.sha256(
            json.dumps(runs, separators=(',', ':')).encode()).hexdigest()}
        data = read(root / f'timing-{case}/samples.json')
        assert data.get('finished_at_utc') and 'failure' not in data
        assert data['semantic_reference'] == expected
        timing = {}
        for label, lane in data['lanes'].items():
            assert lane['program_file_sha256'] == data['lanes']['control1']['program_file_sha256']
            kind = label.removesuffix('1').removesuffix('4')
            assert lane['runtime_sha256'] == sha(root / f'{kind}-runtime')
            entry = {k: lane[k] for k in ('args', 'runtime_sha256', 'program_file_sha256', 'environment')}
            fields = ('iteration', 'inference_seconds', 'process_wall_seconds',
                      'process_user_seconds', 'process_system_seconds', 'phases')
            for group in ('samples', 'warmup_samples'):
                entry[group] = []
                for sample in lane[group]:
                    assert {k: sample[k] for k in expected} == expected
                    assert all(sample['stats'][k] == a['stats'][k] for k in effects)
                    entry[group].append({k: sample[k] for k in fields})
            entry['median_seconds'] = statistics.median(s['inference_seconds'] for s in lane['samples'])
            entry['whole_process_cores_median'] = statistics.median(
                (s['process_user_seconds'] + s['process_system_seconds']) / s['process_wall_seconds']
                for s in lane['samples'])
            timing[label] = entry
        changes = {str(n): 100 * (timing[f'candidate{n}']['median_seconds'] /
                                  timing[f'control{n}']['median_seconds'] - 1) for n in (1, 4)}
        initial = read(root / f'initial-candidate-{case}/report.json')
        result['workloads'][case] = {
            'program_sha256': b['program_sha256'], **expected, 'runs': len(runs),
            'exact_final_state_and_run_summaries': True, 'logical_effects_equal': True,
            'work': {'control': work(a), 'candidate': work(b)},
            'intermediate_work_not_timing': {'coverage_warning': 'event_early_rules is not valid overlap evidence', 'runtime_sha256': sha(root / 'initial-runtime'), 'work': work(initial)},
            'timing': timing, 'candidate_change_percent': changes,
            'execution_order': data['execution_order'],
        }
    ray = result['workloads']['ray']['work']
    assert ray['candidate']['queries']['event_early_rules'] > 0
    assert ray['candidate']['ready_rhs']['event_early_cells'] > 0
    assert ray['candidate']['ready_rhs']['event_completed_early'] > 0
    assert ray['candidate']['constructors']['unit_invalidated'] > 0
    assert ray['candidate']['residual_merge']['merge_pool_calls'] == 0
    assert sum(ray['candidate']['residual_merge']['merge_worker_rows']) > 0
    assert ray['candidate']['conditions']['pool_calls'] < ray['control']['conditions']['pool_calls']
    prior_path=Path(__file__).with_name('preceding-results.json')
    prior=read(prior_path)
    assert prior['candidate_commit']=='4bc89976'
    for case in ('sum','ray'):
        assert prior['workloads'][case]['state_sha256']==result['workloads'][case]['state_sha256']
        assert prior['workloads'][case]['timing']['candidate4']['runtime_sha256']==sha(root/'pre-telemetry-runtime')
    result['preceding_campaign']['sha256']=sha(prior_path)
    result['background_observation']=read(root/'background-observation.json')
    proof = read(root / 'semantic-acceptance.json')
    assert proof['status'] == 'pass'
    assert proof['input_sha256']['cpu_values'] == result['workloads']['sum']['state_sha256']
    result['native_sum_semantic_acceptance'] = {'status': 'pass', 'sha256': sha(root / 'semantic-acceptance.json')}
    return result


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    result = collect(Path(sys.argv[1]))
    Path(sys.argv[2]).write_text(json.dumps(result, indent=2) + '\n')
    print('Completion events, exact final states, Run summaries, native sum contract and every sample verified')
