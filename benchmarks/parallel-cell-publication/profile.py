#!/usr/bin/env python3
"""Sample a frozen runtime against a saved execution, without a timing campaign."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import time


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('runtime', 'program', 'reference', 'output'):
        parser.add_argument(name, type=Path)
    parser.add_argument('--duration', type=int, default=5)
    args = parser.parse_args()
    args.output.mkdir()
    flags = ['--repair-ports', '--entry-publications', '--cell-absorption',
             '--query-workers', '4', '--parallel-residuals', '--parallel-publication']
    command = [str(args.runtime.resolve()), '--program', str(args.program.resolve()),
               '--output', str((args.output / 'runtime').resolve()), *flags]
    env = dict(os.environ, CELL_CPU_PROGRESS='1')
    env.pop('CELL_CPU_PROFILE', None)
    log_path = args.output / 'runtime.log'
    with log_path.open('w') as log:
        process = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 90
            while '[cell-cpu] Run ' not in log_path.read_text():
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError(f'No inference trigger: {log_path}')
                time.sleep(0.02)
            sample = ['/usr/bin/sample', str(process.pid), str(args.duration), '2',
                      '-mayDie', '-file', str((args.output / 'stacks.txt').resolve())]
            with (args.output / 'sample.log').open('w') as sample_log:
                subprocess.run(sample, stdout=sample_log, stderr=subprocess.STDOUT,
                               check=True, timeout=args.duration + 30)
            assert process.wait(timeout=90) == 0, log_path
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
    collect = runpy.run_path(str(Path(__file__).with_name('collect.py')))
    before = collect['read'](args.reference / 'report.json')
    after = collect['read'](args.output / 'runtime/report.json')
    assert before['status'] == after['status'] == 'complete'
    assert before['program_sha256'] == after['program_sha256']
    assert collect['signature'](before) == collect['signature'](after)
    assert before['stats'] == after['stats']
    assert sha(args.reference / 'state.json') == sha(args.output / 'runtime/state.json')
    helpers = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'raytrace-thread-bottlenecks/collect.py'))
    threads = helpers['sample_threads'](args.output / 'stacks.txt')
    result = {'scope': 'standalone Cell CPU; sampled wall stacks, not CPU utilization or speed evidence',
              'runtime_sha256': sha(args.runtime), 'program_file_sha256': sha(args.program),
              'reference_report_sha256': sha(args.reference / 'report.json'),
              'state_sha256': sha(args.output / 'runtime/state.json'),
              'sample': sample, 'stacks_sha256': sha(args.output / 'stacks.txt'),
              'runs': len(after['steps']), 'same_state_ordered_runs_and_graph_counts': True,
              'threads': threads,
              'limits': 'Five-second partial window, progress logging and sampling perturb execution. Inclusive frames overlap. Concurrent external builds may affect residence times.'}
    (args.output / 'diagnostic.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'runs':result['runs'], 'threads':threads}, indent=2))


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    main()
