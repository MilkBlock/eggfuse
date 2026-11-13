#!/usr/bin/env python3
"""Run relevant checks serially in an isolated source checkout."""
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys


def run(checkout, output, target):
    output.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, CARGO_INCREMENTAL='0', CARGO_BUILD_JOBS='1', CARGO_TARGET_DIR=str(target))
    features = 'cell-absorption,view-ports,parallel-publication'
    commands = [
        ('runtime-unit', ['test', '--locked', '-p', 'eggfuse-cell-runtime', '--lib', '--features', features]),
        ('integration', ['test', '--locked', '-p', 'eggfuse-cell-compiler', '--features', features,
                         *[arg for name in ('query_workers', 'parallel_residuals', 'cell_execution',
                            'cell_absorption', 'entry_publications', 'scoped_completion',
                            'completion_batches', 'parallel_publication') for arg in ('--test', name)]]),
        ('legacy', ['check', '--locked', '-p', 'eggfuse-cell-runtime', '--no-default-features']),
        ('all-features', ['check', '--locked', '-p', 'eggfuse-cell-runtime', '--all-features']),
        ('readme-compile', ['cell-compile', '--case', 'sum-bits', '--output', str(output / 'readme-program')]),
        ('readme-run', ['cell-run', '--program', str(output / 'readme-program/program.json'), '--output', str(output / 'readme-run')]),
        ('readme-bench', ['cell-bench', '--program', str(output / 'readme-program/program.json'), '--repeat', '5']),
        ('release', ['build', '--release', '--locked', '-p', 'eggfuse-cell-runtime', '--features', features]),
    ]
    results = []
    for name, args in commands:
        command = ['cargo', *args]
        if name == 'release':
            freeze = runpy.run_path(str(Path(__file__).resolve().parents[2] / 'tools/freeze_runtime.py'))['freeze']
            try:
                evidence = freeze(checkout, target, output / 'candidate-runtime', output / f'{name}.log', features)
                code = 0
            except subprocess.CalledProcessError as error:
                code = error.returncode
            record = dict(name=name, command=command, exit_code=code)
            if not code:
                record['freeze_build'] = evidence
        else:
            with (output / f'{name}.log').open('w') as log:
                code = subprocess.run(command, cwd=checkout, env=env, stdout=log, stderr=subprocess.STDOUT).returncode
            record = dict(name=name, command=command, exit_code=code)
        results.append(record)
        (output / 'validation.json').write_text(json.dumps(results, indent=2) + '\n')
        print(name, code, flush=True)
        if code:
            raise SystemExit(code)


if __name__ == '__main__':
    run(*(Path(arg).resolve() for arg in sys.argv[1:]))
