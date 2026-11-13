#!/usr/bin/env python3
"""Build, freeze and validate both sides of the publication integration serially."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import subprocess
import time

BENCH = Path(__file__).resolve().parents[1]
FEATURES = 'cell-absorption,view-ports,parallel-publication'
CHANGED = {
    'engine/cell-runtime/src/parallel_publication.rs',
    'engine/cell-runtime/src/sieve_publication.rs',
    'engine/cell-runtime/src/sieve_table_events.rs',
    'tools/cell-compiler/tests/parallel_publication.rs',
}


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def run(control, candidate, config, accepted, output, target):
    jobs = runpy.run_path(str(BENCH.parent / 'tools/local_jobs.py'))
    lease = jobs['current_lease']()
    assert lease is not None, 'use the shared compute queue'
    assert not git(control, 'status', '--porcelain'), 'control must be clean'
    commit = git(control, 'rev-parse', 'HEAD')
    assert git(candidate, 'rev-parse', 'HEAD') == commit
    merge = git(candidate, 'rev-parse', 'MERGE_HEAD')
    assert not git(candidate, 'diff', '--name-only', '--diff-filter=U'), 'resolve merge first'
    assert not git(candidate, 'ls-files', '--others', '--exclude-standard')
    assert set(git(candidate, 'diff', 'HEAD', '--name-only').splitlines()) == CHANGED
    patch = subprocess.check_output(['git', '-C', str(candidate), 'diff', 'HEAD', '--binary'])
    output.mkdir(parents=True)
    (output / 'integration.patch').write_bytes(patch)
    sources = {p: sha(candidate / p) for p in sorted(CHANGED)}
    started = time.time()
    build = runpy.run_path(str(BENCH.parent / 'tools/freeze_runtime.py'))['freeze']
    build_evidence = build(control, target, output / 'control-runtime', output / 'control-build.log', FEATURES)
    freeze = runpy.run_path(str(BENCH / 'cell-rhs-boundaries/reference.py'))['run']
    freeze(config, output / 'control', output / 'control-runtime', accepted, commit)
    print('current control frozen', commit, flush=True)
    runpy.run_path(str(BENCH / 'cell-query-fragments/validate.py'))['run'](candidate, output / 'checks', target)
    freeze(output / 'control', output / 'candidate', output / 'checks/candidate-runtime', output / 'control', commit)
    assert sha(output / 'control/candidate-runtime') != sha(output / 'candidate/candidate-runtime'), 'integration must not compare the same executable twice'
    reports = {case: json.loads((output / 'candidate' / f'candidate-{case}/report.json').read_text())
               for case in ('sum', 'ray')}
    assert reports['sum']['publication']['parallel']['admission_bound_rejections'] > 0
    assert reports['ray']['publication']['parallel']['split_entry_tasks'] > 0
    assert git(control, 'rev-parse', 'HEAD') == commit and not git(control, 'status', '--porcelain')
    assert git(candidate, 'rev-parse', 'HEAD') == commit
    assert git(candidate, 'rev-parse', 'MERGE_HEAD') == merge
    assert subprocess.check_output(['git', '-C', str(candidate), 'diff', 'HEAD', '--binary']) == patch
    assert {p: sha(candidate / p) for p in sources} == sources
    result = dict(scope='actual standalone Cell CPU integration; preparation is not timing',
                  control_commit=commit, merge_source=merge, scheduler_job=lease['id'],
                  sources=sources, integration_patch_sha256=sha(output / 'integration.patch'),
                  control_runtime_sha256=sha(output / 'control/candidate-runtime'),
                  candidate_runtime_sha256=sha(output / 'candidate/candidate-runtime'),
                  control_build=build_evidence, features=FEATURES, started=started, finished=time.time())
    (output / 'preparation.json').write_text(json.dumps(result, indent=2) + '\n')
    print('integration preparation passed', flush=True)


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('Run without Python -O')
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('control', 'candidate', 'config', 'accepted', 'output', 'target'):
        parser.add_argument(name, type=Path)
    run(**{k: v.resolve() for k, v in vars(parser.parse_args()).items()})
