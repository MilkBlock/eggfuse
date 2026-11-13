#!/usr/bin/env python3
"""Short four-worker checkpoint: finish all control runs, then all candidate runs.

Each invocation of the established process timer contains exactly one lane.
There is no lane interleaving, concurrent benchmark, sampler or compilation.
"""
import datetime
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import runpy
import subprocess
import sys

_spec = importlib.util.spec_from_file_location('local_jobs', Path(__file__).resolve().parents[2] / 'tools/local_jobs.py')
jobs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(jobs)

timer = runpy.run_path(str(Path(__file__).with_name('measure.py')))
EFFECTS = ('constructor_requests', 'constructor_reused', 'logical_facts_created',
           'function_updates', 'union_requests', 'unions', 'bindings')


def processes():
    # macOS truncates a non-final comm column, even when stdout is a pipe.
    # Keep it last and request wide output so executable names remain usable.
    raw = subprocess.check_output(['ps', '-axww', '-o', 'pid=,pcpu=,comm='], text=True, errors='replace')
    compiler, workloads = [], []
    for line in raw.splitlines():
        fields = line.split(None, 2)
        if len(fields) != 3:
            continue
        category = jobs.classify(fields[2])
        if category == 'compiler':
            compiler.append(line)
        elif category == 'workload':
            workloads.append(line)
    return {'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'compilers': compiler, 'workloads': workloads, 'processes': raw}


def guard(result, output, phase, lane, case, iteration=None):
    observation = dict(processes(), phase=phase, lane=lane, case=case, iteration=iteration)
    if phase.endswith('-sample'):
        # Full snapshots remain at group boundaries. Keep active processes and
        # every guarded executable at sample boundaries, including idle builds.
        keep = set(observation['compilers'] + observation['workloads'])
        observation['processes'] = '\n'.join(line for line in observation['processes'].splitlines()
            if line in keep or (len(line.split(None, 2)) == 3 and float(line.split(None, 2)[1]) >= 1))
        observation['process_scope'] = 'CPU >= 1 percent or guarded compiler/runtime'
    result['observations'].append(observation)
    if observation['compilers'] or observation['workloads']:
        result['measurement_status'] = 'interrupted-by-concurrent-work'
    timer['save'](output / 'progress.json', result)
    if result.get('measurement_status') == 'interrupted-by-concurrent-work':
        raise RuntimeError('Concurrent compiler/runtime detected; retained all samples and interrupted timing')


def verify_frozen_references(result, control, candidate):
    for label, root in (('control', control), ('candidate', candidate)):
        for case in ('sum', 'ray'):
            report = json.loads((root / f'candidate-{case}/report.json').read_text())
            state = root / f'candidate-{case}/state.json'
            if state.exists():
                digest = timer['sha'](state)
            else:
                with gzip.open(str(state) + '.gz', 'rb') as stream:
                    checksum = hashlib.sha256()
                    for block in iter(lambda: stream.read(1 << 20), b''):
                        checksum.update(block)
                    digest = checksum.hexdigest()
            schedule = [[step[k] for k in timer['KEYS']] for step in report['steps']]
            assert result['workloads'][case][label]['semantic_reference'] == {
                'state_sha256': digest,
                'schedule_sha256': hashlib.sha256(json.dumps(schedule, separators=(',', ':')).encode()).hexdigest(),
            }
    proof = json.loads((candidate / 'semantic-acceptance.json').read_text())
    assert proof['status'] == 'pass'
    assert proof['input_sha256']['cpu_values'] == result['workloads']['sum']['candidate']['semantic_reference']['state_sha256']
    result['frozen_references_checked'] = True
    result['native_sum_acceptance_sha256'] = timer['sha'](candidate / 'semantic-acceptance.json')


def run(control, candidate, output, result_path):
    lease = jobs.current_lease()
    if lease is None:
        code = jobs.run_command(jobs.DEFAULT_STATE, [sys.executable, str(Path(__file__).resolve()),
            *map(str, (control, candidate, output, result_path))], kind='timing')
        if code:
            raise RuntimeError(f'Scheduled timing job exited with status {code}')
        return
    if lease['kind'] != 'timing' or lease['guard'] != 'known':
        raise RuntimeError('Timing requires a timing lease with unmanaged-process guards enabled')
    control, candidate, output = (p.resolve() for p in (control, candidate, output))
    changed = subprocess.check_output(['git', 'diff', '--name-only', 'HEAD'], text=True).splitlines()
    assert all(not p.startswith(('engine/', 'tools/')) for p in changed), 'commit tested runtime changes before timing'
    configs = {label: json.loads((root / 'manifest.json').read_text())
               for label, root in (('control', control), ('candidate', candidate))}
    assert output != candidate and output != control
    output.mkdir()
    result = {'scope': 'actual standalone Cell CPU; short sequential four-worker checkpoint',
              'order_policy': 'all control workloads complete before any candidate workload; never interleaved',
              'control_commit': configs['candidate']['control_commit'],
              'candidate_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
              'groups': [], 'workloads': {}, 'observations': []}
    result['scheduler'] = {k: lease[k] for k in ('id', 'kind', 'guard', 'submitted', 'started', 'quiet')}
    for case in ('sum', 'ray'):
        a, b = (configs[label]['lanes'][case] for label in ('control', 'candidate'))
        assert a['program'] == b['program'] and a['args'] == b['args']
        assert a['args'][a['args'].index('--query-workers') + 1] == '4'
    for label, root in (('control', control), ('candidate', candidate)):
        runtime = root / 'candidate-runtime'
        assert timer['sha'](runtime) == configs[label]['runtime_sha256']
        for case, repeat in (('sum', 5), ('ray', 3)):
            guard(result, output, 'before-group', label, case)
            config = configs[label]['lanes'][case]
            lane = {'runtime': str(runtime), 'program': config['program'], 'args': config['args']}
            group = output / f'group-{len(result["groups"]):04d}'
            timer['measure']({'lanes': {label: lane}}, group, repeat, 1, 180,
                sample_boundary=lambda phase, source, iteration: guard(result, output, phase, source, case, iteration))
            raw = json.loads((group / 'samples.json').read_text())
            assert all(order['lanes'] == [label] for order in raw['execution_order'])
            data = raw['lanes'][label]
            report = json.loads((root / f'candidate-{case}/report.json').read_text())
            effects = {k: report['stats'][k] for k in EFFECTS}
            for row in data['warmup_samples'] + data['samples']:
                assert {k: row['stats'][k] for k in EFFECTS} == effects
            workload = result['workloads'].setdefault(case, {})
            if label == 'candidate':
                assert workload['control']['semantic_reference'] == raw['semantic_reference']
                assert workload['control']['logical_effects'] == effects
                assert workload['control']['program_file_sha256'] == data['program_file_sha256']
            keep = ('iteration', 'process_wall_seconds', 'inference_seconds', 'load_seconds',
                    'setup_seconds', 'export_seconds', 'report_seconds',
                    'process_user_seconds', 'process_system_seconds', 'peak_rss_through_inference_bytes')
            workload[label] = {
                'runtime_sha256': data['runtime_sha256'], 'program_file_sha256': data['program_file_sha256'],
                'args': config['args'], 'repeat': repeat, 'warmups': 1,
                'semantic_reference': raw['semantic_reference'], 'logical_effects': effects,
                'medians': data['medians'],
                'samples': [{k: row[k] for k in keep if k in row} for row in data['samples']],
                'warmup_samples': [{k: row[k] for k in keep if k in row} for row in data['warmup_samples']],
                'raw_samples_sha256': timer['sha'](group / 'samples.json'),
            }
            result['groups'].append({'lane': label, 'case': case, 'directory': group.name,
                                     'execution_order': raw['execution_order']})
            guard(result, output, 'after-group', label, case)
    finish(result, control, candidate, result_path)


def finish(result, control, candidate, result_path):
    """Finalize a completed trial; never launch, replace or combine samples."""
    assert [(g['lane'], g['case']) for g in result['groups']] == [
        ('control', 'sum'), ('control', 'ray'), ('candidate', 'sum'), ('candidate', 'ray')]
    assert result['observations'][-1]['phase'] == 'after-group'
    assert not any(o['compilers'] or o['workloads'] for o in result['observations'])
    for case, data in result['workloads'].items():
        before, after = (data[label]['medians']['inference_seconds'] for label in ('control', 'candidate'))
        data['inference_change_percent'] = (after / before - 1) * 100
        data['inference_ranges'] = {label: [min(r['inference_seconds'] for r in data[label]['samples']),
                                           max(r['inference_seconds'] for r in data[label]['samples'])]
                                    for label in ('control', 'candidate')}
        print(case, f'{before:.6f} -> {after:.6f}', f'{data["inference_change_percent"]:+.2f}%', flush=True)
    result['compiler_observed'] = any(o['compilers'] for o in result['observations'])
    result['concurrent_workload_observed'] = any(o['workloads'] for o in result['observations'])
    result['measurement_status'] = 'completed-with-boundary-guards'
    result['both_inference_medians_improved'] = all(
        case['inference_change_percent'] < 0 for case in result['workloads'].values())
    result['interpretation'] = 'Short grouped measurements; full executable names checked before/after every sample, outside timed intervals. Activity wholly between checks, order and thermal/background drift remain possible. No paired/interleaved or statistical-significance claim.'
    verify_frozen_references(result, control, candidate)
    timer['save'](result_path, result)


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    run(*(Path(arg) for arg in sys.argv[1:]))
