#!/usr/bin/env python3
"""Run relevant checks serially in an isolated source checkout."""
import json
import os
from pathlib import Path
import shutil
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
        with (output / f'{name}.log').open('w') as log:
            code = subprocess.run(command, cwd=checkout, env=env, stdout=log, stderr=subprocess.STDOUT).returncode
        results.append(dict(name=name, command=command, exit_code=code))
        (output / 'validation.json').write_text(json.dumps(results, indent=2) + '\n')
        print(name, code, flush=True)
        if code:
            raise SystemExit(code)
    shutil.copy2(target / 'release/eggfuse-cell-runtime', output / 'candidate-runtime')


if __name__ == '__main__':
    run(*(Path(arg).resolve() for arg in sys.argv[1:]))
