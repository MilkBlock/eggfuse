#!/usr/bin/env python3
"""Check frozen execution and distinguish dispatch residence from useful work."""
import hashlib
import json
from pathlib import Path
import runpy
import statistics
import sys


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_phase(p):
    assert p['pooled_calls'] <= p['calls']
    if not p['traced_calls']:
        assert p['tasks'] == 0  # Coarse phases make no task-gap claims.
        return
    assert p['traced_calls'] == p['calls']
    assert sum(p['concurrency_ns']) == p['pool_ns']
    assert p['launch_ns'] + p['task_span_ns'] + p['return_ns'] == p['pool_ns']
    assert p['concurrency_ns'][0] == p['no_task_ns']
    assert sum(i * t for i, t in enumerate(p['concurrency_ns'])) == p['task_elapsed_ns']
    assert sum(p['worker_elapsed_ns']) == p['task_elapsed_ns']
    assert sum(p['worker_tasks']) == p['tasks']


def collect(root, previous):
    base = runpy.run_path(str(Path(__file__).parents[1] / 'raytrace-parallel/measure.py'))
    reference = read(previous / 'candidate-ray/report.json')
    schedule = [[s[k] for k in base['KEYS']] for s in reference['steps']]
    expected = {'state_sha256': sha(previous / 'candidate-ray/state.json'),
                'schedule_sha256': hashlib.sha256(json.dumps(schedule, separators=(',', ':')).encode()).hexdigest()}
    data = read(root / 'timing/samples.json')
    assert data.get('finished_at_utc') and 'failure' not in data
    assert data['semantic_reference'] == expected
    assert data['lanes']['normal']['runtime_sha256'] == sha(previous / 'candidate-runtime')
    assert data['lanes']['pool']['runtime_sha256'] == data['lanes']['inline']['runtime_sha256']
    assert len({lane['program_file_sha256'] for lane in data['lanes'].values()}) == 1
    assert all(lane['args'] == data['lanes']['normal']['args'] for lane in data['lanes'].values())
    effects = ['constructor_requests', 'constructor_reused', 'logical_facts_created',
               'function_updates', 'union_requests', 'unions', 'bindings',
               'unit_registry_batches', 'unit_registry_candidates', 'unit_registry_installs']
    result = {'scope': 'actual standalone Cell CPU, frozen Raytrace, four workers; not native egglog',
              'limits': 'Task residence includes OS descheduling. Pool calls include useful work. No-task gaps include dispatch, wakeup, scheduler and diagnostic overhead; they are not isolated lock time. Inline ablation removes dispatch AND parallelism, so its net delta is not a pure synchronization percentage.',
              'normal_runtime_commit': '3dc84223', 'diagnostic_source_base': 'de03e3d5',
              'reference': expected, 'execution_order': data['execution_order'], 'lanes': {}}
    for label, lane in data['lanes'].items():
        for row in lane['samples'] + lane['warmup_samples']:
            assert {k: row[k] for k in expected} == expected
            assert all(row['stats'][k] == reference['stats'][k] for k in effects)
            if label != 'normal':
                d = row['stats']['sync_diagnostics']
                assert d['inline_registry'] == (label == 'inline')
                for name in ('classify', 'install', 'constructors', 'queries'):
                    check_phase(d[name])
                assert d['classify']['calls'] == d['install']['calls'] == reference['stats']['unit_registry_batches']
                for name in ('classify', 'install'):
                    assert d[name]['pooled_calls'] == (d[name]['calls'] if label == 'pool' else 0)
                    assert d[name]['worker_tasks'][-1] == (d[name]['tasks'] if label == 'inline' else 0)
        fields = ['iteration', 'inference_seconds', 'process_wall_seconds', 'process_user_seconds', 'process_system_seconds', 'phases']
        out = {k: lane[k] for k in ('args', 'environment', 'runtime_sha256', 'program_file_sha256')}
        for group in ('samples', 'warmup_samples'):
            out[group] = [{k: s[k] for k in fields} | {'diagnostic': s['stats'].get('sync_diagnostics')} for s in lane[group]]
        out['inference_median_seconds'] = statistics.median(s['inference_seconds'] for s in lane['samples'])
        if label != 'normal':
            diagnostics = [s['stats']['sync_diagnostics'] for s in lane['samples']]
            out['phase_medians_ms'] = {
                name: {key.removesuffix('_ns'): statistics.median(d[name][key] for d in diagnostics) / 1e6
                       for key in ('prepare_ns', 'pool_ns', 'after_join_ns', 'launch_ns', 'task_span_ns', 'return_ns', 'no_task_ns', 'task_elapsed_ns')}
                for name in ('classify', 'install', 'constructors', 'queries')}
            out['registry_total_median_ms'] = statistics.median(sum(d[n][k] for n in ('classify', 'install') for k in ('prepare_ns', 'pool_ns', 'after_join_ns')) for d in diagnostics) / 1e6
            out['source_adoption_median_ms'] = statistics.median(d['source_adoption_ns'] for d in diagnostics) / 1e6
            out['registered_source_adoption_median_ms'] = statistics.median(d['registered_source_adoption_ns'] for d in diagnostics) / 1e6
        result['lanes'][label] = out
    waits = runpy.run_path(str(Path(__file__).parents[1] / 'cell-peer-results/waits.py'))['profile']
    parse = runpy.run_path(str(Path(__file__).parents[1] / 'raytrace-thread-bottlenecks/collect.py'))['sample_threads']
    result['profiles'] = []
    for name in ('profile-1', 'profile-2', 'quiet-profile-1', 'quiet-profile-2'):
        directory = root / name
        profile = waits(directory)
        profile['name'] = name
        assert {k: profile[k] for k in expected} == expected
        assert profile['runtime_sha256'] == data['lanes']['normal']['runtime_sha256']
        threads = parse(directory / 'stacks.txt')
        main = threads[0]
        profile['main_inference_samples'] = main['inclusive'].get('eggfuse_cell_runtime::executor::Executor::execute_until', 0)
        profile['main_top_inference_inclusive'] = list(main['inference_inclusive'].items())[:35]
        if name.startswith('quiet-'):
            assert profile['main_inference_samples'] / main['samples'] > .98
            assert main['inclusive'].get('std::io::stdio::_eprint', 0) == 0
        profile['main_top_self'] = list(main['own'].items())[:20]
        result['profiles'].append(profile)
    sum_reference = read(previous / 'candidate-sum/report.json')
    sum_state = sha(previous / 'candidate-sum/state.json')
    for mode in (0, 1):
        directory = root / f'sum-{mode}'
        actual = read(directory / 'report.json')
        assert actual['status'] == 'complete'
        assert actual['program_sha256'] == sum_reference['program_sha256']
        assert sha(directory / 'state.json') == sum_state
        assert [[s[k] for k in base['KEYS']] for s in actual['steps']] == [[s[k] for k in base['KEYS']] for s in sum_reference['steps']]
        assert all(actual['stats'][k] == sum_reference['stats'][k] for k in effects)
        assert actual['stats']['sync_diagnostics']['inline_registry'] == bool(mode)
    proof = read(root / 'semantic-acceptance.json')
    assert proof['status'] == 'pass' and proof['input_sha256']['cpu_values'] == sum_state
    result['sum_validation'] = {'exact_final_state_and_ordered_runs': True,
                                'runs': len(sum_reference['steps']), 'state_sha256': sum_state,
                                'native_contract': 'pass', 'proof_sha256': sha(root / 'semantic-acceptance.json')}
    return result


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    Path(sys.argv[3]).write_text(json.dumps(collect(Path(sys.argv[1]), Path(sys.argv[2])), indent=2) + '\n')
