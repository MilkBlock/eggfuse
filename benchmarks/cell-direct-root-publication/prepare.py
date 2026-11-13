#!/usr/bin/env python3
"""Freeze direct root publication and compare it with the current accepted kernel."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import subprocess

ROOT = Path(__file__).resolve().parents[2]
BASE = '58057ef1'
FEATURES = 'cell-absorption,view-ports,parallel-publication'
ENGINE = {'engine/cell-runtime/src/runtime.rs',
          'engine/cell-runtime/src/runtime_cell_writes.rs',
          'engine/cell-runtime/src/stage_spine.rs'}


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True).strip()


def prepare(accepted, target, output):
    lease = runpy.run_path(str(ROOT / 'tools/local_jobs.py'))['current_lease']()
    assert lease is not None and lease['kind'] == 'compute'
    assert not git('status', '--porcelain')
    commit, base = git('rev-parse', 'HEAD'), git('rev-parse', BASE)
    prior = json.loads((accepted / 'validation.json').read_text())
    # Reuse the accepted frozen control only if its compiled source is unchanged.
    assert not git('diff', prior['source_commit'], base, '--name-only', '--',
                   'engine', 'Cargo.toml', 'Cargo.lock')
    assert set(git('diff', base, commit, '--name-only', '--', 'engine').splitlines()) == ENGINE
    assert prior['build']['features'] == FEATURES
    old = accepted / 'candidate'
    control_sha = json.loads((old / 'manifest.json').read_text())['runtime_sha256']
    assert control_sha == prior['build']['runtime_sha256']
    with (old / 'candidate-runtime').open('rb') as stream:
        assert hashlib.file_digest(stream, 'sha256').hexdigest() == control_sha
    output.mkdir(parents=True)
    (output / 'control').symlink_to(old, target_is_directory=True)
    freeze = runpy.run_path(str(ROOT / 'tools/freeze_runtime.py'))['freeze']
    reference = runpy.run_path(str(ROOT / 'benchmarks/cell-rhs-boundaries/reference.py'))['run']
    build = freeze(ROOT, target, output / 'runtime', output / 'build.log', FEATURES)
    assert build['runtime_sha256'] != control_sha
    reference(old, output / 'candidate', output / 'runtime', old, base)
    result = dict(scope='actual standalone Cell CPU; work and semantics, not timing',
                  source_commit=commit, control_commit=base,
                  reused_control_commit=prior['source_commit'],
                  control_runtime_sha256=control_sha, build=build, workloads={})
    stage_keys = ('absorbed_root_checks', 'absorbed_root_completions', 'captured_contexts',
                  'inline_function_receipts', 'inline_function_reads', 'cell_output_receipts',
                  'completion_cell_visits', 'receipt_attempts', 'receipt_redirects',
                  'captured_anchors', 'anchor_publications', 'publication_seconds')
    for case in ('sum', 'ray'):
        reports = [json.loads((p / f'candidate-{case}/report.json').read_text())
                   for p in (old, output / 'candidate')]
        for field in ('resumed_steps', 'completed_steps', 'root_attempts', 'max_chain',
                      'block_resumptions', 'captured_anchors', 'anchor_publications'):
            assert reports[0]['stage_spine']['stats'][field] == reports[1]['stage_spine']['stats'][field], (case, field)
        for field in ('batches', 'candidates', 'inherited_candidates', 'rows', 'invalidated'):
            assert reports[0]['cell_execution']['runtime']['stats']['writes'][field] == reports[1]['cell_execution']['runtime']['stats']['writes'][field], (case, field)
        result['workloads'][case] = {
            lane: dict(stage={k: r['stage_spine']['stats'][k] for k in stage_keys},
                       entry=r['entry_schedule']['stats'],
                       writes=r['cell_execution']['runtime']['stats']['writes'])
            for lane, r in zip(('control', 'candidate'), reports)}
    ray = result['workloads']['ray']
    assert ray['candidate']['stage']['captured_contexts'] < ray['control']['stage']['captured_contexts']
    assert ray['candidate']['stage']['inline_function_reads'] < ray['control']['stage']['inline_function_reads']
    assert git('rev-parse', 'HEAD') == commit and not git('status', '--porcelain')
    (output / 'validation.json').write_text(json.dumps(result, indent=2) + '\n')
    print('Direct root publication: exact Runs/effects/states and reduced pending completions verified', flush=True)


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('Run without Python -O')
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('accepted', 'target', 'output'):
        parser.add_argument(name, type=Path)
    prepare(**{k: v.resolve() for k, v in vars(parser.parse_args()).items()})
