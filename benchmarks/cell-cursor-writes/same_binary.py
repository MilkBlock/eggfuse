#!/usr/bin/env python3
"""Freeze one CPU-instrumented runtime with selected Cursor writes off/on."""
import argparse
import json
from pathlib import Path
import runpy
import subprocess

ROOT = Path(__file__).resolve().parents[2]
FEATURES = 'cell-absorption,view-ports,parallel-publication,inference-cpu'


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True).strip()


def prepare(accepted, target, output):
    lease = runpy.run_path(str(ROOT / 'tools/local_jobs.py'))['current_lease']()
    assert lease is not None and lease['kind'] == 'compute'
    assert not git('status', '--porcelain'), 'commit the checked source before freezing'
    commit = git('rev-parse', 'HEAD')
    output.mkdir(parents=True)
    freeze = runpy.run_path(str(ROOT / 'tools/freeze_runtime.py'))['freeze']
    reference = runpy.run_path(str(ROOT / 'benchmarks/cell-rhs-boundaries/reference.py'))['run']
    build = freeze(ROOT, target, output / 'runtime', output / 'build.log', FEATURES)
    evidence = dict(scope='actual standalone Cell CPU; same-binary Cursor-write diagnostic, not ordinary speed acceptance',
                    features=FEATURES, scheduler_job=lease['id'], lanes={})
    for lane in ('control', 'candidate'):
        config = json.loads((accepted / 'candidate/manifest.json').read_text())
        if lane == 'control':
            for case in ('sum', 'ray'):
                config['lanes'][case]['args'].append('--serial-cursor-writes')
        source = output / f'config-{lane}'
        source.mkdir()
        (source / 'manifest.json').write_text(json.dumps(config, indent=2) + '\n')
        reference(source, output / lane, output / 'runtime', accepted / 'candidate', commit)
        counts = {}
        for case in ('sum', 'ray'):
            report = json.loads((output / lane / f'candidate-{case}/report.json').read_text())
            prior = json.loads((accepted / lane / f'candidate-{case}/report.json').read_text())
            state = report['cell_execution']['runtime']
            assert state['cursor_writes'] == (lane == 'candidate')
            assert report['inference_cpu']['wall_seconds'] > 0
            assert 'storage' not in report and 'sync_diagnostics' not in report['stats']
            counts[case] = state['stats']['writes']
            old = prior['cell_execution']['runtime']['stats']['writes']
            for field in ('batches', 'candidates', 'inherited_candidates', 'rows', 'invalidated'):
                assert counts[case][field] == old.get(field, 0), (lane, case, field)
            for field in ('resumed_steps', 'completed_steps', 'root_attempts', 'max_chain', 'block_resumptions'):
                assert report['stage_spine']['stats'][field] == prior['stage_spine']['stats'][field]
        evidence['lanes'][lane] = dict(diagnostic_commit=commit, build=build, writes=counts)
    assert git('rev-parse', 'HEAD') == commit and not git('status', '--porcelain')
    (output / 'preparation.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print('Identical binaries: old/new write coverage, source Runs, effects and semantic acceptance passed', flush=True)


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('Run without Python -O')
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('accepted', 'target', 'output'):
        parser.add_argument(name, type=Path)
    prepare(**{k: v.resolve() for k, v in vars(parser.parse_args()).items()})
