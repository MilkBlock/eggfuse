#!/usr/bin/env python3
"""Freeze identical CPU instrumentation on both sides, or summarize completed trials."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import statistics
import subprocess

ROOT = Path(__file__).resolve().parents[2]
FEATURES = 'cell-absorption,view-ports,parallel-publication,inference-cpu'
SOURCES = ('engine/cell-runtime/Cargo.toml', 'engine/cell-runtime/src/main.rs',
           'engine/cell-runtime/src/inference_cpu.rs')
BASES = {'control': '03065edb300a62e868aa950c2d7af5eacc98ed32',
         'candidate': '50e3822a65a85c9a7a35648a52a732afa0a06e29'}
WAITS = {
    'query_event_seconds': 'query_workers.stats.event_wait_ns',
    'rhs_event_seconds': 'cell_execution.runtime.stats.scheduler.event_wait_ns',
    'rhs_scope_seconds': 'cell_execution.runtime.stats.scheduler.wait_ns',
    'birth_scope_seconds': 'cell_execution.runtime.stats.births.worker_wait_ns',
    'registry_event_seconds': 'stats.unit_registry_event_wait_ns',
}


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def save(path, data):
    path.write_text(json.dumps(data, indent=2) + '\n')


def prepare(control, candidate, accepted, target, output):
    jobs = runpy.run_path(str(ROOT / 'tools/local_jobs.py'))
    lease = jobs['current_lease']()
    assert lease is not None, 'use the shared compute queue'
    output.mkdir(parents=True)
    build = runpy.run_path(str(ROOT / 'tools/freeze_runtime.py'))['freeze']
    reference = runpy.run_path(str(ROOT / 'benchmarks/cell-rhs-boundaries/reference.py'))['run']
    evidence = {'scope': 'actual standalone Cell CPU diagnostics, not speed acceptance',
                'features': FEATURES, 'scheduler_job': lease['id'], 'lanes': {}}
    for label, checkout in (('control', control), ('candidate', candidate)):
        assert not git(checkout, 'status', '--porcelain')
        assert git(checkout, 'rev-parse', 'HEAD^') == BASES[label]
        assert set(git(checkout, 'diff', 'HEAD^', '--name-only').splitlines()) == set(SOURCES)
        sources = {p: sha(checkout / p) for p in SOURCES}
        if label == 'candidate':
            assert sources == evidence['lanes']['control']['sources'], 'instrumentation differs'
        commit = git(checkout, 'rev-parse', 'HEAD')
        frozen = build(checkout, target, output / f'{label}-runtime', output / f'{label}-build.log', FEATURES)
        reference(accepted / label, output / label, output / f'{label}-runtime', accepted / label,
                  BASES['control'])
        reports = {case: json.loads((output / label / f'candidate-{case}/report.json').read_text())
                   for case in ('sum', 'ray')}
        for report in reports.values():
            assert report['inference_cpu']['wall_seconds'] > 0
            assert 'storage' not in report, 'do not enable storage-metrics'
            assert 'sync_diagnostics' not in report['stats'], 'no per-task tracing in this trial'
        if label == 'candidate':
            assert reports['sum']['publication']['parallel']['admission_bound_rejections'] > 0
            assert reports['ray']['publication']['parallel']['split_entry_tasks'] > 0
        else:
            assert reports['ray']['publication']['parallel'].get('split_entry_tasks', 0) == 0
        assert git(checkout, 'rev-parse', 'HEAD') == commit and not git(checkout, 'status', '--porcelain')
        assert sources == {p: sha(checkout / p) for p in SOURCES}
        evidence['lanes'][label] = dict(base_commit=BASES[label], diagnostic_commit=commit,
                                       sources=sources, build=frozen)
        save(output / 'preparation.json', evidence)
    assert evidence['lanes']['control']['build']['runtime_sha256'] != evidence['lanes']['candidate']['build']['runtime_sha256']
    print('CPU diagnostic binaries frozen; state, Run, effects and native sum contract passed', flush=True)


def at(value, path):
    for key in path.split('.'):
        value = value[key]
    return value


def metrics(row):
    cpu = row['inference_cpu']
    wall = cpu['wall_seconds']
    total = cpu['process_user_seconds'] + cpu['process_system_seconds']
    main = cpu['coordinator_cpu_seconds']
    assert wall > 0 and total > 0 and main >= 0
    return {
        'wall_seconds': wall,
        'process_cpu_seconds': total,
        'coordinator_cpu_seconds': main,
        'other_threads_cpu_seconds': total - main,
        'mean_consumed_cores': total / wall,
        'coordinator_off_cpu_seconds': wall - main,
        'coordinator_off_cpu_fraction': (wall - main) / wall,
        'capture_seconds': cpu['boundary_capture_seconds'],
        'voluntary_switches': cpu['voluntary_context_switches'],
        'involuntary_switches': cpu['involuntary_context_switches'],
        **{name: at(row, path) * 1e-9 for name, path in WAITS.items()},
    }


def summarize(preparation, timing, output):
    prep = json.loads((preparation / 'preparation.json').read_text())
    trial_path = timing.with_name(timing.name + '.json')
    trial = json.loads(trial_path.read_text())
    assert trial['measurement_status'] == 'completed-with-boundary-guards'
    assert trial['frozen_references_checked']
    assert [(g['lane'], g['case']) for g in trial['groups']] == [
        ('control', 'sum'), ('control', 'ray'), ('candidate', 'sum'), ('candidate', 'ray')]
    assert trial['observations'][-1]['phase'] == 'after-group'
    assert not any(o['compilers'] or o['workloads'] for o in trial['observations'])
    result = dict(scope=prep['scope'], preparation=prep, scheduler=trial['scheduler'],
                  guards=len(trial['observations']), workloads={}, trial_sha256=sha(trial_path),
                  interpretation='Each ratio is computed per sample before taking its median. Process CPU/wall is mean cores, not worker utilization. Off-CPU includes scheduling and blocking. Existing wait spans can overlap; do not add them or call them pure synchronization. Instrumented sequential groups do not replace ordinary speed acceptance.',
                  wait_fields=WAITS)
    for group in trial['groups']:
        lane, case = group['lane'], group['case']
        raw_path = timing / group['directory'] / 'samples.json'
        raw = json.loads(raw_path.read_text())['lanes'][lane]
        assert raw['runtime_sha256'] == prep['lanes'][lane]['build']['runtime_sha256']
        samples = [dict(iteration=r['iteration'], **metrics(r)) for r in raw['samples']]
        medians = {k: statistics.median(s[k] for s in samples) for k in samples[0] if k != 'iteration'}
        result['workloads'].setdefault(case, {})[lane] = dict(
            medians=medians, samples=samples, warmups=[metrics(r) for r in raw['warmup_samples']],
            raw_sha256=sha(raw_path))
    for case, lanes in result['workloads'].items():
        a, b = (lanes[k]['medians'] for k in ('control', 'candidate'))
        lanes['change_percent'] = {k: (b[k] / a[k] - 1) * 100 for k in (
            'wall_seconds', 'process_cpu_seconds', 'coordinator_cpu_seconds', 'mean_consumed_cores')}
        print(case, json.dumps(lanes['change_percent']), flush=True)
    save(output, result)


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('Run without Python -O')
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    p = sub.add_parser('prepare')
    for name in ('control', 'candidate', 'accepted', 'target', 'output'):
        p.add_argument(name, type=Path)
    p = sub.add_parser('summarize')
    for name in ('preparation', 'timing', 'output'):
        p.add_argument(name, type=Path)
    args = vars(parser.parse_args())
    action = args.pop('action')
    globals()[action](**{k: p.resolve() for k, p in args.items()})
