#!/usr/bin/env python3
"""Prepare the fifth-change comparison from already frozen, verified runtimes."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def read(path):
    return json.loads(path.read_text())


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def prepare(root):
    here = Path(__file__).parent
    manifest = read(root / 'manifest.json')
    evidence = read(here / 'results.json')
    assert evidence['candidate_runtime_sha256'] == manifest['runtime_sha256']
    current = subprocess.check_output(['git', 'rev-parse', '--short=8', 'HEAD'], text=True).strip()
    runtimes = {
        'historical': Path('out/cell-events/control-runtime').resolve(),
        'checkpoint': Path('out/cell-fact-lease/candidate-runtime').resolve(),
        'control': Path('out/cell-fused-registration/candidate-runtime').resolve(),
        'candidate': (root / 'candidate-runtime').resolve(),
    }
    saved = read(here.parent / 'cell-fact-lease/timing-results.json')['workloads']['ray']['lanes']
    expected = {'historical': saved['historical4']['runtime_sha256'],
                'checkpoint': saved['candidate4']['runtime_sha256'],
                'control': evidence['control_runtime_sha256'],
                'candidate': manifest['runtime_sha256']}
    assert {k: sha(p) for k, p in runtimes.items()} == expected
    revisions = {'historical': '8335929d', 'checkpoint': '916ebf7c',
                 'control': '076a923a', 'candidate': current}
    assert not (root / 'runtime-revisions.json').exists(), 'use a fresh campaign root'
    (root / 'runtime-revisions.json').write_text(json.dumps(revisions, indent=2) + '\n')
    for case in ('sum', 'ray'):
        config = manifest['lanes'][case]
        lanes = {}
        for name, runtime in runtimes.items():
            for workers in (1, 4):
                args = config['args'].copy()
                args[args.index('--query-workers') + 1] = str(workers)
                lanes[f'{name}{workers}'] = {'runtime': str(runtime),
                                           'program': config['program'], 'args': args}
        (root / f'{case}-manifest.json').write_text(json.dumps({'lanes': lanes}, indent=2) + '\n')


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    prepare(Path(sys.argv[1]).resolve())
