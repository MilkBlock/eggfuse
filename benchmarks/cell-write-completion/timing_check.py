#!/usr/bin/env python3
"""Check every periodic timing sample and the separate quiet stack profiles."""
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


def collect(root):
    revisions = {'historical': '8335929d', 'checkpoint': '2ae7b97e',
                 'control': 'c27cbcf1', 'candidate': '79e6fe0f'}
    evidence = read(Path(__file__).with_name('results.json'))
    effects = ('constructor_requests', 'constructor_reused', 'logical_facts_created',
               'function_updates', 'union_requests', 'unions', 'bindings')
    result = {
        'scope': 'actual standalone Cell CPU, not native egglog performance',
        'runtime_revisions': revisions,
        'limits': 'All samples and warmups retained. Ambient load and within-lane variation are material; median differences are not established causal speedups. CPU/wall includes load and export, not inference-only utilization. Profiles are separate diagnostic executions, not timing samples.',
        'work_evidence_sha256': sha(Path(__file__).with_name('results.json')),
        'workloads': {},
    }
    for case, repeat in (('sum', 5), ('ray', 3)):
        path = root / f'timing-{case}/samples.json'
        data = read(path)
        manifest = read(root / f'{case}-manifest.json')
        expected = {k: evidence['workloads'][case][k]
                    for k in ('state_sha256', 'schedule_sha256')}
        assert data.get('finished_at_utc') and 'failure' not in data
        assert data['repeat'] == repeat and data['warmups'] == 1
        assert data['semantic_reference'] == expected
        labels = {f'{revision}{n}' for revision in revisions for n in (1, 4)}
        assert set(data['lanes']) == set(manifest['lanes']) == labels
        assert len(data['execution_order']) == repeat + 1
        assert {x['iteration'] for x in data['execution_order']} == set(range(-1, repeat))
        assert all(len(x['lanes']) == len(labels) and set(x['lanes']) == labels
                   for x in data['execution_order'])
        report = read(root / f'candidate-{case}/report.json')
        lanes = {}
        for label, lane in data['lanes'].items():
            config = manifest['lanes'][label]
            workers = int(label[-1])
            assert lane['args'] == config['args']
            assert lane['args'][lane['args'].index('--query-workers') + 1] == str(workers)
            assert lane['runtime_sha256'] == sha(Path(config['runtime']))
            assert lane['program_file_sha256'] == sha(Path(config['program']))
            assert lane['environment'] == config.get('environment', {})
            out = {k: lane[k] for k in ('args', 'environment', 'runtime_sha256', 'program_file_sha256')}
            out['logical_effects'] = {k: report['stats'][k] for k in effects}
            for group, iterations in (('samples', range(repeat)), ('warmup_samples', range(-1, 0))):
                assert len(lane[group]) == len(iterations)
                assert {s['iteration'] for s in lane[group]} == set(iterations)
                out[group] = []
                for sample in lane[group]:
                    assert {k: sample[k] for k in expected} == expected
                    assert sample['runs'] == evidence['workloads'][case]['runs']
                    assert all(sample['stats'][k] == report['stats'][k] for k in effects)
                    fields = ('iteration', 'inference_seconds', 'process_wall_seconds',
                              'process_user_seconds', 'process_system_seconds', 'phases',
                              'key_lookup_calls')
                    out[group].append({k: sample[k] for k in fields})
            times = [s['inference_seconds'] for s in lane['samples']]
            out['inference_median_seconds'] = statistics.median(times)
            out['inference_range_seconds'] = [min(times), max(times)]
            out['whole_process_cores_median'] = statistics.median(
                (s['process_user_seconds'] + s['process_system_seconds']) / s['process_wall_seconds']
                for s in lane['samples'])
            lanes[label] = out
        assert len({v['program_file_sha256'] for v in lanes.values()}) == 1
        for revision in revisions:
            assert lanes[revision + '1']['runtime_sha256'] == lanes[revision + '4']['runtime_sha256']
        comparisons = {}
        for prior in ('historical', 'checkpoint', 'control'):
            comparisons[prior] = {}
            for n in (1, 4):
                current = lanes[f'candidate{n}']
                old = lanes[f'{prior}{n}']
                paired = [100 * (a['inference_seconds'] / b['inference_seconds'] - 1)
                          for a, b in zip(sorted(current['samples'], key=lambda s: s['iteration']),
                                          sorted(old['samples'], key=lambda s: s['iteration']))]
                comparisons[prior][str(n)] = {
                    'median_change_percent': 100 * (current['inference_median_seconds'] /
                                                    old['inference_median_seconds'] - 1),
                    'iteration_paired_change_percent': paired,
                    'paired_median_change_percent': statistics.median(paired),
                }
        result['workloads'][case] = {
            **expected, 'runs': evidence['workloads'][case]['runs'],
            'samples_file_sha256': sha(path), 'manifest': manifest,
            **{k: data[k] for k in ('repeat', 'warmups', 'seed', 'started_at_utc',
                                   'finished_at_utc', 'execution_order')},
            'lanes': lanes, 'candidate_comparisons': comparisons,
            'four_worker_speedup_over_one': {
                rev: lanes[rev + '1']['inference_median_seconds'] /
                     lanes[rev + '4']['inference_median_seconds'] for rev in revisions},
        }
    parse = runpy.run_path(str(Path(__file__).parents[1] / 'raytrace-thread-bottlenecks/collect.py'))['sample_threads']
    waits = runpy.run_path(str(Path(__file__).parents[1] / 'cell-peer-results/waits.py'))['profile']
    profiles = {}
    for label in ('control4', 'candidate4'):
        directory = root / f'profile-{label}'
        profile = waits(directory)
        lane = result['workloads']['ray']['lanes'][label]
        for k in ('state_sha256', 'schedule_sha256'):
            assert profile[k] == result['workloads']['ray'][k]
        for k in ('runtime_sha256', 'program_file_sha256'):
            assert profile[k] == lane[k]
        assert profile['sample']['progress_logging'] is False
        threads = parse(directory / 'stacks.txt')
        main = threads[0]
        inference = main['inclusive']['eggfuse_cell_runtime::executor::Executor::execute_until']
        assert inference / main['samples'] > .98
        assert main['inclusive'].get('std::io::stdio::_eprint', 0) == 0
        selected = ('Executor::matches', 'Scheduler::batches', 'finish_queries',
                    'publish_finished_tables', 'repair_selected', 'write_cells', '__psynch_cvwait')
        profile['main_inference_samples'] = inference
        profile['main_selected_inclusive'] = {
            key: sum(n for s, n in main['inference_inclusive'].items() if s.endswith(key))
            for key in selected}
        profile['selected_limits'] = 'Inclusive frames overlap and include callees and waits; do not sum. Worker condition waits include both pool idle and inside-job waits. Context classification is heuristic. Five-second windows are partial, sampled wall residence, not CPU percentages or isolated synchronization costs.'
        profile['thread_top_inclusive'] = [list(t['inclusive'].items())[:60] for t in threads]
        profile['main_top_self'] = list(main['own'].items())[:30]
        profiles[label] = profile
    result['profiles'] = profiles
    background = read(root / 'background-observation.json')
    result['background_observation'] = {k: v for k, v in background.items() if k != 'processes'}
    # Keep ambient-load evidence without copying the entire desktop process inventory.
    result['background_observation']['nonzero_cpu_processes'] = [
        line for line in background['processes'].splitlines()[1:]
        if float(line.rsplit(None, 1)[-1]) > 0]
    result['background_observation']['full_snapshot_sha256'] = sha(root / 'background-observation.json')
    proof = read(root / 'semantic-acceptance.json')
    assert proof['status'] == 'pass'
    assert proof['input_sha256']['cpu_values'] == result['workloads']['sum']['state_sha256']
    result['native_sum_acceptance'] = {'status': 'pass', 'sha256': sha(root / 'semantic-acceptance.json')}
    return result


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    Path(sys.argv[2]).write_text(json.dumps(collect(Path(sys.argv[1])), indent=2) + '\n')
    print('Every timing sample, warmup, runtime, state, Run summary and quiet profile verified')
