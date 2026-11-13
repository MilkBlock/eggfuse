#!/usr/bin/env python3
"""Validate selected-Cursor scalar writes, then freeze both exact source trees."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess

ROOT = Path(__file__).resolve().parents[2]
FEATURES = 'cell-absorption,view-ports,parallel-publication'
FILES = ('engine/cell-runtime/src/cell_writes.rs',
         'engine/cell-runtime/src/runtime_cell_writes.rs',
         'tools/cell-compiler/tests/cell_execution.rs')


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def run(control, accepted, target, output):
    lease = runpy.run_path(str(ROOT / 'tools/local_jobs.py'))['current_lease']()
    assert lease is not None, 'use the shared compute queue'
    base = git(control, 'rev-parse', 'HEAD')
    assert not git(control, 'status', '--porcelain')
    head = git(ROOT, 'rev-parse', 'HEAD')
    subprocess.run(['git', '-C', str(ROOT), 'merge-base', '--is-ancestor', base, head], check=True)
    # Accept both an uncommitted candidate and the committed experiment. Its
    # documentation/harness may also differ; the runtime/test delta is exact.
    changed = git(ROOT, 'diff', '--name-only', base, '--', 'engine', 'tools').splitlines()
    assert set(changed) == set(FILES), changed
    sources = {p: sha(ROOT / p) for p in FILES}
    output.mkdir(parents=True)
    patch = subprocess.check_output(['git', '-C', str(ROOT), 'diff', base, '--binary', '--', *FILES])
    (output / 'implementation.patch').write_bytes(patch)
    env = dict(os.environ, CARGO_INCREMENTAL='0', CARGO_BUILD_JOBS='1', CARGO_TARGET_DIR=str(target))
    commands = [
        ('ordered-integration', ['test', '--locked', '-p', 'eggfuse-cell-compiler',
            '--features', FEATURES + ',iterative-bake', '--test', 'cell_execution',
            '--test', 'query_workers', '--test', 'query_receipts', '--test', 'matched_handoffs',
            '--test', 'entry_publications', '--test', 'parallel_publication']),
    ]
    checks = []
    for name, args in commands:
        with (output / f'{name}.log').open('w') as log:
            code = subprocess.run(['cargo', *args], cwd=ROOT, env=env,
                                  stdout=log, stderr=subprocess.STDOUT).returncode
        checks.append(dict(name=name, args=args, exit_code=code))
        (output / 'checks.json').write_text(json.dumps(checks, indent=2) + '\n')
        assert code == 0, name
    # Existing validation also exercises unit/legacy/all-feature and README paths.
    runpy.run_path(str(ROOT / 'benchmarks/cell-query-fragments/validate.py'))['run'](
        ROOT, output / 'checks', target)
    freeze = runpy.run_path(str(ROOT / 'tools/freeze_runtime.py'))['freeze']
    reference = runpy.run_path(str(ROOT / 'benchmarks/cell-rhs-boundaries/reference.py'))['run']
    build = freeze(control, target, output / 'control-runtime', output / 'control-build.log', FEATURES)
    reference(accepted, output / 'control', output / 'control-runtime', accepted, base)
    reference(output / 'control', output / 'candidate', output / 'checks/candidate-runtime', output / 'control', base)
    assert sha(output / 'control/candidate-runtime') != sha(output / 'candidate/candidate-runtime')
    assert {p: sha(ROOT / p) for p in FILES} == sources
    assert git(ROOT, 'rev-parse', 'HEAD') == head
    result = dict(scope='actual standalone Cell CPU; work and semantic checks, not timing',
                  base_commit=base, candidate_head=head, features=FEATURES, scheduler_job=lease['id'],
                  patch_sha256=sha(output / 'implementation.patch'), sources=sources,
                  control_build=build, workloads={})
    for case in ('sum', 'ray'):
        reports = {lane: json.loads((output / lane / f'candidate-{case}/report.json').read_text())
                   for lane in ('control', 'candidate')}
        result['workloads'][case] = {lane: {
            'writes': r['cell_execution']['runtime']['stats']['writes'],
            'stage': {k: r['stage_spine']['stats'][k] for k in (
                'resumed_steps', 'completed_steps', 'root_attempts', 'max_chain',
                'block_resumptions', 'history_slots_written', 'anchor_publications')},
            'runtime_sha256': sha(output / lane / 'candidate-runtime'),
        } for lane, r in reports.items()}
        for key in ('resumed_steps', 'completed_steps', 'root_attempts', 'max_chain', 'block_resumptions'):
            assert result['workloads'][case]['control']['stage'][key] == result['workloads'][case]['candidate']['stage'][key], key
    (output / 'results.json').write_text(json.dumps(result, indent=2) + '\n')
    print('Cursor write checks and frozen states passed', flush=True)
    for case, lanes in result['workloads'].items():
        print(case, 'inherited candidates', lanes['candidate']['writes']['inherited_candidates'], flush=True)


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('Run without Python -O')
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('control', 'accepted', 'target', 'output'):
        p.add_argument(name, type=Path)
    run(**{k: v.resolve() for k, v in vars(p.parse_args()).items()})
