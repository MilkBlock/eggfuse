#!/usr/bin/env python3
"""Check and time a source-preserving Raytrace catalog on one frozen runtime.

The catalog has bounded per-Run graph/binding audits plus full-program final
state, source Run summaries and effect counts. This is differential acceptance,
not a native Raytrace proof. All control samples precede candidate samples.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import runpy
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
quick = runpy.run_path(str(ROOT / 'benchmarks/raytrace-parallel/quick.py'))
timer = quick['timer']
EFFECTS = (*quick['EFFECTS'], 'merge_calls')
read = lambda path: json.loads(path.read_text())
sha = runpy.run_path(str(ROOT / 'benchmarks/cell-bake-full-merge/check.py'))['sha']


def check(accepted, original_audit, program, candidate_audit, output):
    lease = quick['jobs'].current_lease()
    assert __debug__ and lease and lease['kind'] == 'compute'
    config = read(accepted / 'manifest.json')
    lane = config['lanes']['ray']
    original = Path(lane['program'])
    a, b = read(original), read(program)
    metadata = {'sha256', 'ownership_fragments', 'ownership_markers', 'ownership_witnesses'}
    assert {k:v for k,v in a.items() if k not in metadata} == {k:v for k,v in b.items() if k not in metadata}
    prefixes = [read(p / 'control.json') for p in (original_audit, candidate_audit)]
    for raw, prefix, directory in zip((a, b), prefixes, (original_audit, candidate_audit)):
        assert prefix['schema'] == 'eggfuse-worker-prefix-audit/v1'
        assert prefix['program_sha256'] == raw['sha256']
        assert prefix['runs'] == prefix['run_limit'] > 0
        assert len(prefix['run_checks']) == prefix['runs']
        observed = read(directory / 'trace.json')
        assert observed['all_saved_run_checks_equal'] and observed['run_checks'] == prefix['run_checks']
        assert observed['catalog_trace']['catalog_sha256'] == raw['sha256']
    assert prefixes[0]['configuration'] == prefixes[1]['configuration']
    assert prefixes[0]['run_checks'] == prefixes[1]['run_checks'], 'catalog changed a checked source boundary'
    assert lane['args'] == ['--repair-ports', '--entry-publications', '--cell-absorption',
        '--query-workers', '4', '--parallel-residuals', '--parallel-publication',
        '--cell-execution-grain', '1', '--cell-ownership']
    assert sha(accepted / 'candidate-runtime') == config['runtime_sha256']
    output.mkdir(exist_ok=False)
    binary = output / 'candidate-runtime'
    shutil.copy2(accepted / 'candidate-runtime', binary)
    reference = read(accepted / 'candidate-ray/report.json')
    schedule = [[s[k] for k in timer['KEYS']] for s in reference['steps']]
    state = sha(accepted / 'candidate-ray/state.json')
    proof = dict(state_sha256=state,
        schedule_sha256=hashlib.sha256(json.dumps(schedule, separators=(',', ':')).encode()).hexdigest())
    result = dict(scope=__doc__, runtime_sha256=config['runtime_sha256'], scheduler=lease,
        prefix_runs=prefixes[0]['runs'], prefix_inputs={str(p):sha(p / 'control.json') for p in (original_audit, candidate_audit)},
        semantic_reference=proof, lanes={})
    for name, source in [('control', original), ('candidate', program)]:
        destination = output / name
        command = [str(binary), '--program', str(source), '--output', str(destination), *lane['args']]
        with (output / f'{name}.log').open('w') as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
        report = read(destination / 'report.json')
        assert report['status'] == 'complete'
        assert report['program_sha256'] == read(source)['sha256']
        assert sha(destination / 'state.json') == state
        assert [[s[k] for k in timer['KEYS']] for s in report['steps']] == schedule
        assert all(report['stats'][k] == reference['stats'][k] for k in EFFECTS)
        with (destination / 'state.json').open('rb') as inp, gzip.open(destination / 'state.json.gz', 'wb', compresslevel=1) as out:
            shutil.copyfileobj(inp, out)
        (destination / 'state.json').unlink()
        result['lanes'][name] = dict(program=str(source), program_file_sha256=sha(source), args=lane['args'],
            key_lookup_calls=report['key_lookup_calls'], ownership=report['cell_ownership']['stats'],
            work={k:v for k,v in report['stats'].items() if k.startswith('constructor_prefix_')})
        print(name, len(schedule), 'Run summaries, effects, final state exact;', report['key_lookup_calls'], 'lookups', flush=True)
    result['status'] = 'pass'
    (output / 'validation.json').write_text(json.dumps(result, indent=2)+'\n')


def measure(validated, output, repeats):
    lease = quick['jobs'].current_lease()
    assert __debug__ and lease and lease['kind'] == 'timing' and lease['guard'] == 'known'
    assert repeats > 0
    proof = read(validated / 'validation.json')
    assert proof['status'] == 'pass'
    binary = validated / 'candidate-runtime'
    assert sha(binary) == proof['runtime_sha256']
    output.mkdir(exist_ok=False)
    result = dict(scope='same-binary four-worker Raytrace catalog; differential contract, not native proof',
        order_policy='entire control then entire candidate; never interleaved', scheduler=lease,
        observations=[], lanes={}, validation_sha256=sha(validated / 'validation.json'))
    for name in ('control', 'candidate'):
        lane = proof['lanes'][name]
        assert sha(Path(lane['program'])) == lane['program_file_sha256']
        group = output / name
        quick['guard'](result, output, 'before-group', name, 'ray')
        timer['measure']({'lanes':{name:dict(runtime=str(binary),program=lane['program'],args=lane['args'])}},
            group, repeats, 1, 180,
            sample_boundary=lambda phase, source, iteration: quick['guard'](result,output,phase,source,'ray',iteration))
        raw = read(group / 'samples.json')
        assert raw['semantic_reference'] == proof['semantic_reference']
        assert all(row['lanes'] == [name] for row in raw['execution_order'])
        report = read(validated / name / 'report.json')
        data = raw['lanes'][name]
        for row in data['warmup_samples'] + data['samples']:
            assert all(row['stats'][k] == report['stats'][k] for k in EFFECTS)
        result['lanes'][name] = dict(medians=data['medians'],
            inference_samples=[s['inference_seconds'] for s in data['samples']],
            raw_samples_sha256=sha(group / 'samples.json'))
        quick['guard'](result, output, 'after-group', name, 'ray')
    a,b = [result['lanes'][n]['medians']['inference_seconds'] for n in ('control','candidate')]
    result['inference_change_percent'] = (b/a-1)*100
    result['measurement_status'] = 'completed-with-boundary-guards'
    (output / 'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(f'Raytrace: {a:.6f} -> {b:.6f} ({result["inference_change_percent"]:+.2f}%)')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command',required=True)
    check_parser = sub.add_parser('check')
    for name in ('accepted','original_audit','program','candidate_audit','output'):
        check_parser.add_argument(name,type=Path)
    timing_parser = sub.add_parser('time')
    for name in ('validated','output'):
        timing_parser.add_argument(name,type=Path)
    timing_parser.add_argument('--repeats',type=int,default=3)
    args = vars(parser.parse_args())
    action = check if args.pop('command') == 'check' else measure
    action(**args)
