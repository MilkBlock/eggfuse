#!/usr/bin/env python3
"""One frozen learned-catalog diagnostic; all control samples precede candidate."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[2]
quick = runpy.run_path(str(ROOT / 'benchmarks/raytrace-parallel/quick.py'))
timer = quick['timer']


def run(artifacts, program, output, repeats=7):
    lease = quick['jobs'].current_lease()
    assert __debug__ and lease and lease['kind'] == 'timing' and lease['guard'] == 'known'
    assert repeats > 0
    work = json.loads((artifacts / 'work.json').read_text())
    proof = work['learned_validation']
    assert proof['exact_state_runs_effects'] and timer['sha'](program) == proof['program_sha256']
    output.mkdir(exist_ok=False)
    result = dict(scope='actual standalone Cell CPU; learned-catalog diagnostic, no native acceptance',
                  order_policy='all control samples, then all candidate samples; never interleaved',
                  commits=work['commits'], scheduler=lease, observations=[], lanes={})
    reference_args = None
    for name in ('control', 'candidate'):
        root = artifacts / name
        config = json.loads((root / 'checked/manifest.json').read_text())
        binary = root / 'checked/candidate-runtime'
        assert timer['sha'](binary) == config['runtime_sha256'] == work['lanes'][name]['build']['runtime_sha256']
        args = config['lanes']['sum']['args']
        if reference_args is None:
            reference_args = args
        assert args == reference_args and args[args.index('--query-workers') + 1] == '4'
        quick['guard'](result, output, 'before-group', name, 'learned')
        group = output / name
        timer['measure']({'lanes': {name: dict(runtime=str(binary), program=str(program), args=args)}},
                         group, repeats, 1, 180,
                         sample_boundary=lambda phase, source, iteration:
                             quick['guard'](result, output, phase, source, 'learned', iteration))
        raw = json.loads((group / 'samples.json').read_text())
        assert all(order['lanes'] == [name] for order in raw['execution_order'])
        report = json.loads((root / 'learned/report.json').read_text())
        schedule = [[s[k] for k in timer['KEYS']] for s in report['steps']]
        assert raw['semantic_reference'] == dict(state_sha256=proof['state_sha256'],
            schedule_sha256=hashlib.sha256(json.dumps(schedule, separators=(',', ':')).encode()).hexdigest())
        data = raw['lanes'][name]
        for row in data['warmup_samples'] + data['samples']:
            assert all(row['stats'][k] == report['stats'][k] for k in quick['EFFECTS'])
        result['lanes'][name] = dict(medians=data['medians'],
            inference_samples=[s['inference_seconds'] for s in data['samples']],
            runtime_sha256=data['runtime_sha256'], program_sha256=data['program_file_sha256'],
            raw_samples_sha256=timer['sha'](group / 'samples.json'))
        quick['guard'](result, output, 'after-group', name, 'learned')
    a, b = [result['lanes'][name]['medians']['inference_seconds'] for name in ('control', 'candidate')]
    result['inference_change_percent'] = (b / a - 1) * 100
    result['measurement_status'] = 'completed-with-boundary-guards'
    result['interpretation'] = 'Short grouped diagnostic; order, thermal drift and activity between guards remain possible.'
    timer['save'](output / 'result.json', result)
    print(f'learned: {a:.6f} -> {b:.6f} ({result["inference_change_percent"]:+.2f}%)', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('artifacts', 'program', 'output'):
        parser.add_argument(name, type=Path)
    parser.add_argument('--repeats', type=int, default=7)
    run(**vars(parser.parse_args()))
