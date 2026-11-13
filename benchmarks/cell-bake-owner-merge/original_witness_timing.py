#!/usr/bin/env python3
"""Time original-source witness installation with one frozen runtime, whole lanes."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[2]
quick = runpy.run_path(str(ROOT / 'benchmarks/raytrace-parallel/quick.py'))
timer = quick['timer']


def read(path):
    return json.loads(path.read_text())


def run(artifacts, witnesses, output, repeats=9):
    lease = quick['jobs'].current_lease()
    assert lease and lease['kind'] == 'timing' and lease['guard'] == 'known' and repeats > 0
    old = read(artifacts / 'original-workers/result.json')
    new = read(witnesses / 'worker-check/result.json')
    manifest = read(artifacts / 'candidate/checked/manifest.json')
    runtime = artifacts / 'candidate/checked/candidate-runtime'
    binary = timer['sha'](runtime)
    assert old['status'] == new['status'] == 'pass'
    assert old['runtime_sha256'] == new['runtime_sha256'] == manifest['runtime_sha256'] == binary
    a, b = old['lanes']['round1'], new['lanes']['round1-witnesses']
    for key in ('state_sha256', 'stage_sha256', 'bindings_sha256', 'runs'):
        assert a[key] == b[key]
    native = read(artifacts / 'candidate/checked/semantic-acceptance.json')
    assert native['status'] == 'pass' and native['input_sha256']['cpu_values'] == a['state_sha256']
    output.mkdir(exist_ok=False)
    result = dict(scope='actual four-worker Cell CPU; same runtime and original source, witness catalog only',
                  runtime_commit=old['commit'], runtime_sha256=binary, scheduler=lease,
                  order_policy='all control samples, then all candidate samples; never interleaved',
                  audit_sha256={'control': timer['sha'](artifacts / 'original-workers/result.json'),
                                'candidate': timer['sha'](witnesses / 'worker-check/result.json')},
                  observations=[], lanes={})
    reference = None
    for name, evidence, report_root in [('control', a, artifacts / 'original-workers/round1'),
                                       ('candidate', b, witnesses / 'worker-check/round1-witnesses')]:
        program = Path(evidence['program'])
        assert timer['sha'](program) == evidence['program_sha256']
        report = read(report_root / 'report.json')
        schedule = [[s[k] for k in timer['KEYS']] for s in report['steps']]
        semantic = dict(state_sha256=evidence['state_sha256'],
                        schedule_sha256=hashlib.sha256(json.dumps(schedule, separators=(',', ':')).encode()).hexdigest())
        if reference is None:
            reference = semantic
        assert semantic == reference
        group = output / name
        quick['guard'](result, output, 'before-group', name, 'original-witnesses')
        timer['measure']({'lanes': {name: dict(runtime=str(runtime), program=str(program),
                                             args=manifest['lanes']['sum']['args'])}}, group, repeats, 1, 180,
                         sample_boundary=lambda phase, lane, iteration:
                             quick['guard'](result, output, phase, lane, 'original-witnesses', iteration))
        raw = read(group / 'samples.json')
        assert raw['semantic_reference'] == semantic
        assert all(order['lanes'] == [name] for order in raw['execution_order'])
        data = raw['lanes'][name]
        for sample in data['warmup_samples'] + data['samples']:
            assert all(sample['stats'][k] == report['stats'][k] for k in quick['EFFECTS'])
            assert sample['key_lookup_calls'] == report['key_lookup_calls']
        result['lanes'][name] = dict(medians=data['medians'], samples=[s['inference_seconds'] for s in data['samples']],
                                    program_sha256=data['program_file_sha256'], raw_samples_sha256=timer['sha'](group / 'samples.json'))
        quick['guard'](result, output, 'after-group', name, 'original-witnesses')
    before, after = [result['lanes'][name]['medians']['inference_seconds'] for name in ('control', 'candidate')]
    result['change_percent'] = (after / before - 1) * 100
    result['measurement_status'] = 'completed-with-boundary-guards'
    result['interpretation'] = 'Short grouped diagnostic, not a stable-speedup claim. Order and machine drift remain possible.'
    timer['save'](output / 'result.json', result)
    print(f'{before:.6f} -> {after:.6f} ({result["change_percent"]:+.2f}%)')


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('Run without Python -O')
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('artifacts', 'witnesses', 'output'):
        parser.add_argument(name, type=Path)
    parser.add_argument('--repeats', type=int, default=9)
    run(**vars(parser.parse_args()))
