#!/usr/bin/env python3
"""Frozen catalog timing, optionally with ordinary cases; whole control first."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[2]
quick = runpy.run_path(str(ROOT / 'benchmarks/raytrace-parallel/quick.py'))
timer = quick['timer']


def run(artifacts, program, output, repeats=7, include_ordinary=False):
    lease = quick['jobs'].current_lease()
    assert __debug__ and lease and lease['kind'] == 'timing' and lease['guard'] == 'known'
    assert repeats > 0
    work = json.loads((artifacts / 'work.json').read_text())
    proof = work['learned_validation']
    assert proof['exact_state_runs_effects'] and timer['sha'](program) == proof['program_sha256']
    output.mkdir(exist_ok=False)
    result = dict(scope='actual standalone Cell CPU; native acceptance only for ordinary sum-bits, learned catalog is differential',
                  order_policy='all control samples, then all candidate samples; never interleaved',
                  commits=work['commits'], scheduler=lease, observations=[], workloads={}, groups=[])
    cases = [('sum',5),('ray',3),('learned',repeats)] if include_ordinary else [('learned',repeats)]
    references = {}
    for name in ('control', 'candidate'):
        root = artifacts / name
        config = json.loads((root / 'checked/manifest.json').read_text())
        binary = root / 'checked/candidate-runtime'
        assert timer['sha'](binary) == config['runtime_sha256'] == work['lanes'][name]['build']['runtime_sha256']
        for case, count in cases:
            lane = config['lanes']['sum' if case == 'learned' else case]
            args = lane['args']
            source_program = program if case == 'learned' else Path(lane['program'])
            assert args[args.index('--query-workers') + 1] == '4'
            if case == 'learned':
                report_root, state_hash = root / 'learned', proof['state_sha256']
            else:
                report_root = root / f'checked/candidate-{case}'
                validation = json.loads((root / 'checked/validation.json').read_text())[case]
                assert validation['exact_state_runs_effects']
                state_hash = validation['state_sha256']
                if case == 'sum':
                    native = json.loads((root / 'checked/semantic-acceptance.json').read_text())
                    assert native['status'] == 'pass' and native['input_sha256']['cpu_values'] == state_hash
            report = json.loads((report_root / 'report.json').read_text())
            schedule = [[s[k] for k in timer['KEYS']] for s in report['steps']]
            reference = dict(state_sha256=state_hash,
                schedule_sha256=hashlib.sha256(json.dumps(schedule,separators=(',', ':')).encode()).hexdigest())
            identity = (str(source_program), args, reference)
            if name == 'control':
                references[case] = identity
            assert identity == references[case]
            quick['guard'](result, output, 'before-group', name, case)
            group = output / f'{name}-{case}'
            timer['measure']({'lanes': {name: dict(runtime=str(binary), program=str(source_program), args=args)}},
                             group, count, 1, 180,
                             sample_boundary=lambda phase, source, iteration:
                                 quick['guard'](result, output, phase, source, case, iteration))
            raw = json.loads((group / 'samples.json').read_text())
            assert all(order['lanes'] == [name] for order in raw['execution_order'])
            assert raw['semantic_reference'] == reference
            data = raw['lanes'][name]
            for row in data['warmup_samples'] + data['samples']:
                assert all(row['stats'][k] == report['stats'][k] for k in quick['EFFECTS'])
            workload = result['workloads'].setdefault(case,{})
            workload[name] = dict(medians=data['medians'],
                inference_samples=[s['inference_seconds'] for s in data['samples']],
                runtime_sha256=data['runtime_sha256'], program_sha256=data['program_file_sha256'],
                raw_samples_sha256=timer['sha'](group / 'samples.json'))
            result['groups'].append((name,case))
            quick['guard'](result, output, 'after-group', name, case)
    assert result['groups'] == [(name,case) for name in ('control','candidate') for case,_ in cases]
    for case, data in result['workloads'].items():
        a,b = [data[name]['medians']['inference_seconds'] for name in ('control','candidate')]
        data['inference_change_percent'] = (b / a - 1) * 100
        print(f'{case}: {a:.6f} -> {b:.6f} ({data["inference_change_percent"]:+.2f}%)', flush=True)
    if not include_ordinary:
        learned = result.pop('workloads')['learned']
        result['inference_change_percent'] = learned.pop('inference_change_percent')
        result['lanes'] = learned
    result['measurement_status'] = 'completed-with-boundary-guards'
    result['interpretation'] = 'Short grouped diagnostic; order, thermal drift and activity between guards remain possible.'
    timer['save'](output / 'result.json', result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('artifacts', 'program', 'output'):
        parser.add_argument(name, type=Path)
    parser.add_argument('--repeats', type=int, default=7)
    parser.add_argument('--include-ordinary', action='store_true',
                        help='also time sum-bits (5 samples) and Raytrace (3), still whole control before candidate')
    run(**vars(parser.parse_args()))
