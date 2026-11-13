#!/usr/bin/env python3
"""Freeze a release runtime without trusting a shared target's cached launcher."""
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess


def freeze(checkout, target, destination, log_path, features):
    jobs = runpy.run_path(str(Path(__file__).with_name('local_jobs.py')))
    lease = jobs['current_lease']()
    if lease is None:
        raise RuntimeError('Freeze builds require the shared job queue')
    if destination.exists():
        raise FileExistsError(destination)
    env = dict(os.environ, CARGO_INCREMENTAL='0', CARGO_BUILD_JOBS='1', CARGO_TARGET_DIR=str(target))
    # Different worktrees/features can leave a current fingerprint beside a
    # top-level executable from another build. Rebuild this release package;
    # retain dependency and debug caches. Never use an unscoped cargo clean.
    commands = [
        ['cargo', 'clean', '--release', '-p', 'eggfuse-cell-runtime'],
        ['cargo', 'build', '--release', '--locked', '-p', 'eggfuse-cell-runtime', '--features', features],
    ]
    with log_path.open('w') as log:
        for command in commands:
            log.write(json.dumps(command) + '\n')
            log.flush()
            subprocess.run(command, cwd=checkout, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    binary = target / 'release/eggfuse-cell-runtime'
    shutil.copy2(binary, destination)
    hasher = hashlib.sha256()
    with destination.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            hasher.update(chunk)
    digest = hasher.hexdigest()
    evidence = dict(commands=commands, checkout=str(checkout), target=str(target),
                    runtime_sha256=digest, features=features, scheduler_job=lease['id'])
    destination.with_name(destination.name + '.build.json').write_text(json.dumps(evidence, indent=2) + '\n')
    return evidence
