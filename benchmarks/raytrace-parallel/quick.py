#!/usr/bin/env python3
"""Short four-worker checkpoint: finish all control runs, then all candidate runs.

Each invocation of the established process timer contains exactly one lane.
There is no lane interleaving, concurrent benchmark, sampler or compilation.
"""
import datetime
import gzip
import hashlib
import json
from pathlib import Path
import runpy
import subprocess
import sys

timer = runpy.run_path(str(Path(__file__).with_name('measure.py')))
EFFECTS = ('constructor_requests', 'constructor_reused', 'logical_facts_created',
           'function_updates', 'union_requests', 'unions', 'bindings')


def processes():
    raw = subprocess.check_output(['ps', '-axo', 'pid,comm,pcpu'], text=True, errors='replace')
    compiler = [line for line in raw.splitlines()[1:]
                if Path(line.split(None, 1)[1].rsplit(None, 1)[0].strip()).name in ('cargo', 'rustc')]
    return {'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'compilers': compiler, 'processes': raw}


def verify_frozen_references(result, control, candidate):
    for label, root in (('control', control), ('candidate', candidate)):
        for case in ('sum', 'ray'):
            report = json.loads((root / f'candidate-{case}/report.json').read_text())
            state = root / f'candidate-{case}/state.json'
            if state.exists():
                digest = timer['sha'](state)
            else:
                with gzip.open(str(state) + '.gz', 'rb') as stream:
                    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
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
    for case in ('sum', 'ray'):
        a, b = (configs[label]['lanes'][case] for label in ('control', 'candidate'))
        assert a['program'] == b['program'] and a['args'] == b['args']
        assert a['args'][a['args'].index('--query-workers') + 1] == '4'
    for label, root in (('control', control), ('candidate', candidate)):
        runtime = root / 'candidate-runtime'
        assert timer['sha'](runtime) == configs[label]['runtime_sha256']
        for case, repeat in (('sum', 5), ('ray', 3)):
            observation = processes()
            result['observations'].append(observation)
            timer['save'](output / 'progress.json', result)
            if observation['compilers']:
                raise RuntimeError('Compiler active before timing group; retained earlier groups without discarding samples')
            config = configs[label]['lanes'][case]
            lane = {'runtime': str(runtime), 'program': config['program'], 'args': config['args']}
            group = output / f'group-{len(result["groups"]):04d}'
            timer['measure']({'lanes': {label: lane}}, group, repeat, 1, 180)
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
            result['observations'].append(processes())
            timer['save'](output / 'progress.json', result)
    for case, data in result['workloads'].items():
        before, after = (data[label]['medians']['inference_seconds'] for label in ('control', 'candidate'))
        data['inference_change_percent'] = (after / before - 1) * 100
        data['inference_ranges'] = {label: [min(r['inference_seconds'] for r in data[label]['samples']),
                                           max(r['inference_seconds'] for r in data[label]['samples'])]
                                    for label in ('control', 'candidate')}
        print(case, f'{before:.6f} -> {after:.6f}', f'{data["inference_change_percent"]:+.2f}%', flush=True)
    result['compiler_observed'] = any(o['compilers'] for o in result['observations'])
    result['both_inference_medians_improved'] = all(
        case['inference_change_percent'] < 0 for case in result['workloads'].values())
    result['interpretation'] = 'Short grouped measurements; order and thermal/background drift remain possible. No paired/interleaved or statistical-significance claim.'
    verify_frozen_references(result, control, candidate)
    timer['save'](result_path, result)


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    run(*(Path(arg) for arg in sys.argv[1:]))
