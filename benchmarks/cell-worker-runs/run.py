#!/usr/bin/env python3
"""Freeze the candidate and execute unchanged work/semantic inputs once."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys


def run(control, output, runtime, *, control_commit='c0dd0034'):
    output.mkdir(parents=True, exist_ok=True)
    binary = output / 'candidate-runtime'
    assert not binary.exists(), 'use a fresh artifact root'
    shutil.copy2(runtime, binary)
    with binary.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    original = json.loads((control / 'manifest.json').read_text())
    manifest = {'scope': 'actual standalone Cell CPU work and semantics; not timing',
                'control_commit': control_commit, 'runtime_sha256': digest, 'lanes': {}}
    for case in ('sum', 'ray'):
        config = original['lanes'][case]
        destination = output / f'candidate-{case}'
        assert not destination.exists()
        command = [str(binary), '--program', config['program'], '--output', str(destination), *config['args']]
        with (output / f'{case}.log').open('w') as log:
            code = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=180).returncode
        manifest['lanes'][case] = dict(command=command, program=config['program'], args=config['args'], exit_code=code)
        (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        print(case, code, flush=True)
        if code:
            raise SystemExit(code)


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    run(*(Path(arg).resolve() for arg in sys.argv[1:]))
