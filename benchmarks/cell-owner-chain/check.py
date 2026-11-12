#!/usr/bin/env python3
"""Validate the actual Cell CPU owner chain; retain all interleaved samples."""
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
    base = runpy.run_path(str(Path(__file__).parents[1] / 'raytrace-parallel/measure.py'))
    result = {'scope': 'actual standalone Cell CPU, not native egglog performance',
              'control_commit': '9a0353cf', 'candidate_commit': '8335929d', 'workloads': {}}
    effects = ('constructor_requests', 'constructor_reused', 'logical_facts_created',
               'function_updates', 'union_requests', 'unions', 'bindings')
    for case in ('sum', 'ray'):
        directories = [root / f'{lane}-{case}' for lane in ('control', 'candidate')]
        a, b = (read(p / 'report.json') for p in directories)
        assert a['status'] == b['status'] == 'complete'
        assert a['program_sha256'] == b['program_sha256']
        state = sha(directories[0] / 'state.json')
        assert state == sha(directories[1] / 'state.json')
        runs = [[s[k] for k in base['KEYS']] for s in a['steps']]
        assert runs == [[s[k] for k in base['KEYS']] for s in b['steps']]
        assert all(a['stats'][k] == b['stats'][k] for k in effects)
        samples = read(root / f'timing-{case}/samples.json')
        assert samples.get('finished_at_utc') and 'failure' not in samples
        expected = {'state_sha256': state, 'schedule_sha256': hashlib.sha256(
            json.dumps(runs, separators=(',', ':')).encode()).hexdigest()}
        assert samples['semantic_reference'] == expected
        timing = {}
        for label, lane in samples['lanes'].items():
            kind = label.removesuffix('1').removesuffix('4')
            assert lane['runtime_sha256'] == sha(root / f'{kind}-runtime')
            for sample in lane['samples'] + lane['warmup_samples']:
                assert {k: sample[k] for k in expected} == expected
                assert all(sample['stats'][k] == a['stats'][k] for k in effects)
            fields = ('iteration', 'inference_seconds', 'process_wall_seconds',
                      'process_user_seconds', 'process_system_seconds', 'phases')
            timing[label] = {k: lane[k] for k in ('args', 'runtime_sha256', 'program_file_sha256')}
            for group in ('samples', 'warmup_samples'):
                timing[label][group] = [{k: sample[k] for k in fields} for sample in lane[group]]
            timing[label]['median_seconds'] = statistics.median(s['inference_seconds'] for s in lane['samples'])
            timing[label]['process_cores_median'] = statistics.median(
                (s['process_user_seconds'] + s['process_system_seconds']) / s['process_wall_seconds']
                for s in lane['samples'])
        work = {}
        for label, report in (('control', a), ('candidate', b)):
            q = report['query_workers']['stats']
            work[label] = {
                'queries': {k: v for k, v in q.items() if k.startswith(('owned_', 'entry_range_'))
                            or k in ('entries', 'entry_headers', 'point_reads', 'cell_task_probes',
                                     'borrowed_job_headers', 'chunks', 'task_order_headers',
                                     'completion_headers', 'completion_error_checks')},
                'key_lookup_calls': report['key_lookup_calls'],
                'entries': report['entry_schedule']['stats'],
                'publication': report['publication'],
                'execution': q['execution'],
                'candidate_storage': report['stage_spine']['query_candidate_storage'],
            }
        if case == 'ray':
            q, e = work['candidate']['queries'], work['candidate']['entries']
            assert q['owned_range_answers'] > 0 and q['owned_support_rejections'] > 0
            assert e['worker_entry_updates'] > 0
            assert q['entry_headers'] < work['control']['queries']['entry_headers']
        result['workloads'][case] = {'program_sha256': b['program_sha256'], **expected,
            'runs': len(runs), 'exact_final_state_and_ordered_run_summaries': True,
            'logical_effects_equal': True, 'work': work, 'timing': timing,
            'execution_order': samples['execution_order']}
    proof = read(root / 'semantic-acceptance.json')
    assert proof['status'] == 'pass'
    assert proof['input_sha256']['cpu_values'] == result['workloads']['sum']['state_sha256']
    result['semantic_acceptance'] = {'status': 'pass', 'sha256': sha(root / 'semantic-acceptance.json')}
    profile = runpy.run_path(str(Path(__file__).parents[1] / 'cell-peer-results/waits.py'))['profile']
    parse = runpy.run_path(str(Path(__file__).parents[1] / 'raytrace-thread-bottlenecks/collect.py'))['sample_threads']
    result['profiles'] = []
    for label in ('control4', 'candidate4'):
        directory = root / f'profile-{label}'
        p = profile(directory)
        p['lane'] = label
        assert p['runtime_sha256'] == result['workloads']['ray']['timing'][label]['runtime_sha256']
        assert all(p[k] == result['workloads']['ray'][k] for k in ('state_sha256', 'schedule_sha256'))
        main = parse(directory / 'stacks.txt')[0]
        p['main_inference_samples'] = main['inclusive'].get('eggfuse_cell_runtime::executor::Executor::execute_until', 0)
        p['main_inference_inclusive'] = list(main['inference_inclusive'].items())[:40]
        assert not p['sample']['progress_logging']
        result['profiles'].append(p)
    return result


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    Path(sys.argv[2]).write_text(json.dumps(collect(Path(sys.argv[1])), indent=2) + '\n')
    print('Cell ownership, ordered Runs, final contract and all samples verified')
