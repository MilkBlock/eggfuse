#!/usr/bin/env python3
"""Freeze an ordinary source-instance candidate against a saved or current control."""
import argparse
import json
from pathlib import Path
import runpy
import subprocess

ROOT = Path(__file__).resolve().parents[2]
FEATURES = 'cell-absorption,view-ports,parallel-publication'


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True).strip()


def prepare(accepted, target, output, control_checkout=None):
    lease = runpy.run_path(str(ROOT / 'tools/local_jobs.py'))['current_lease']()
    assert lease is not None and lease['kind'] == 'compute'
    assert not git('status', '--porcelain')
    commit = git('rev-parse', 'HEAD')
    base = json.loads((accepted / 'candidate/manifest.json').read_text())['control_commit']
    output.mkdir(parents=True)
    freeze = runpy.run_path(str(ROOT / 'tools/freeze_runtime.py'))['freeze']
    reference = runpy.run_path(str(ROOT / 'benchmarks/cell-rhs-boundaries/reference.py'))['run']
    control_build = None
    if control_checkout is not None:
        def control_git(*args):
            return subprocess.check_output(['git', '-C', str(control_checkout), *args], text=True).strip()
        assert not control_git('status', '--porcelain')
        base = control_git('rev-parse', 'HEAD')
        assert set(git('diff', base, '--name-only', '--', 'engine').splitlines()) == {
            'engine/cell-runtime/src/cell_writes.rs', 'engine/cell-runtime/src/runtime_cell_writes.rs'}
        control_build = freeze(control_checkout, target, output / 'control-runtime', output / 'control-build.log', FEATURES)
        reference(accepted / 'candidate', output / 'control', output / 'control-runtime', accepted / 'candidate', base)
        assert control_git('rev-parse', 'HEAD') == base and not control_git('status', '--porcelain')
    else:
        (output / 'control').symlink_to(accepted / 'control', target_is_directory=True)
    build = freeze(ROOT, target, output / 'runtime', output / 'build.log', FEATURES)
    reference(accepted / 'candidate', output / 'candidate', output / 'runtime', accepted / 'candidate', base)
    result = dict(scope='actual standalone Cell CPU; ordinary build work/semantic checks, not timing',
                  source_commit=commit, control_commit=base, control_build=control_build, build=build, workloads={})
    for case in ('sum', 'ray'):
        old_root = output / 'control' if control_checkout is not None else accepted / 'candidate'
        old = json.loads((old_root / f'candidate-{case}/report.json').read_text())
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
    parser.add_argument('--control-checkout', type=Path, help='freeze this clean current baseline instead of reusing the original control')
    prepare(**{k: v.resolve() if v is not None else None for k, v in vars(parser.parse_args()).items()})
