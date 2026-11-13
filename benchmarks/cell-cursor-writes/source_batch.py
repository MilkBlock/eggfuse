#!/usr/bin/env python3
"""Freeze the source-instance handoff change against the original ordinary control."""
import argparse
import json
from pathlib import Path
import runpy
import subprocess

ROOT = Path(__file__).resolve().parents[2]
FEATURES = 'cell-absorption,view-ports,parallel-publication'


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True).strip()


def prepare(accepted, target, output):
    lease = runpy.run_path(str(ROOT / 'tools/local_jobs.py'))['current_lease']()
    assert lease is not None and lease['kind'] == 'compute'
    assert not git('status', '--porcelain')
    commit = git('rev-parse', 'HEAD')
    base = json.loads((accepted / 'candidate/manifest.json').read_text())['control_commit']
    output.mkdir(parents=True)
    freeze = runpy.run_path(str(ROOT / 'tools/freeze_runtime.py'))['freeze']
    reference = runpy.run_path(str(ROOT / 'benchmarks/cell-rhs-boundaries/reference.py'))['run']
    build = freeze(ROOT, target, output / 'runtime', output / 'build.log', FEATURES)
    (output / 'control').symlink_to(accepted / 'control', target_is_directory=True)
    reference(accepted / 'candidate', output / 'candidate', output / 'runtime', accepted / 'candidate', base)
    result = dict(scope='actual standalone Cell CPU; ordinary build work/semantic checks, not timing',
                  source_commit=commit, control_commit=base, build=build, workloads={})
    for case in ('sum', 'ray'):
        old = json.loads((accepted / 'candidate' / f'candidate-{case}/report.json').read_text())
        new = json.loads((output / 'candidate' / f'candidate-{case}/report.json').read_text())
        a, b = [r['cell_execution']['runtime']['stats']['writes'] for r in (old, new)]
        for field in ('batches', 'candidates', 'inherited_candidates', 'rows', 'invalidated'):
            assert a[field] == b[field], (case, field)
        for field in ('resumed_steps', 'completed_steps', 'root_attempts', 'max_chain', 'block_resumptions'):
            assert old['stage_spine']['stats'][field] == new['stage_spine']['stats'][field]
        assert b['origin_token_bytes'] == 0
        assert 'inference_cpu' not in new
        result['workloads'][case] = dict(previous=a, candidate=b)
    assert git('rev-parse', 'HEAD') == commit and not git('status', '--porcelain')
    (output / 'validation.json').write_text(json.dumps(result, indent=2) + '\n')
    print('Source-instance handoff: exact work coverage, Runs, effects and semantic acceptance passed', flush=True)


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('Run without Python -O')
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('accepted', 'target', 'output'):
        parser.add_argument(name, type=Path)
    prepare(**{k: v.resolve() for k, v in vars(parser.parse_args()).items()})
