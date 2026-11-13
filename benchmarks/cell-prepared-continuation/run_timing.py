#!/usr/bin/env python3
"""Run the authorized five-implementation checkpoint after committing the change."""
import datetime
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import threading


def snapshot():
    processes = subprocess.check_output(['ps', '-axo', 'comm,pcpu'], text=True, errors='replace')
    return {'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'compiler_processes': [line for line in processes.splitlines()[1:]
                                   if Path(line.rsplit(None, 1)[0].strip()).name in ('rustc', 'cargo')],
            'platform': platform.platform(), 'processes': processes}


def run(root):
    changed = subprocess.check_output(['git', 'diff', '--name-only', 'HEAD'], text=True).splitlines()
    assert all(p.startswith('benchmarks/') or p == 'README.md' for p in changed), 'commit runtime changes before timing'
    root = root.resolve()
    source = json.loads((root / 'manifest.json').read_text())
    assert source['control_commit'] == '64f022a8'
    revisions = {'historical': '8335929d', 'checkpoint': '8df9de2a', 'control': '64f022a8',
                 'candidate': subprocess.check_output(['git', 'rev-parse', '--short=8', 'HEAD'], text=True).strip()}
    runtimes = {'historical': root.parent / 'cell-events/control-runtime',
                'checkpoint': root.parent / 'cell-completion-slots/candidate-runtime',
                'control': root.parent / 'cell-bake-refresh/candidate-runtime',
                'candidate': root / 'candidate-runtime'}
    previous = json.loads((Path(__file__).parents[1] / 'cell-completion-slots/timing-results.json').read_text())
    evidence = json.loads(Path(__file__).with_name('results.json').read_text())
    assert previous['runtime_revisions']['historical'] == revisions['historical']
    assert previous['runtime_revisions']['candidate'] == revisions['checkpoint']
    expected = {'historical': previous['workloads']['ray']['lanes']['historical4']['runtime_sha256'],
                'checkpoint': previous['workloads']['ray']['lanes']['candidate4']['runtime_sha256'],
                'control': evidence['control_runtime_sha256'], 'candidate': source['runtime_sha256']}
    for revision, runtime in runtimes.items():
        with runtime.open('rb') as stream:
            assert hashlib.file_digest(stream, 'sha256').hexdigest() == expected[revision], revision
    for case in ('sum', 'ray'):
        assert not (root / f'timing-{case}').exists(), 'use a fresh timing root'
        config = source['lanes'][case]
        lanes = {}
        for revision, runtime in runtimes.items():
            for workers in (1, 4):
                args = list(config['args'])
                args[args.index('--query-workers') + 1] = str(workers)
                lanes[f'{revision}{workers}'] = {'runtime': str(runtime), 'program': config['program'], 'args': args}
        (root / f'{case}-manifest.json').write_text(json.dumps({'lanes': lanes}, indent=2) + '\n')
    (root / 'runtime-revisions.json').write_text(json.dumps(revisions, indent=2) + '\n')
    observation = snapshot()
    (root / 'background-observation.json').write_text(json.dumps(observation, indent=2) + '\n')
    if observation['compiler_processes']:
        raise RuntimeError('A compiler is active; retain this observation and wait for that process before timing')
    stop = threading.Event()

    def monitor():
        with (root / 'background-samples.jsonl').open('w') as stream:
            while True:
                stream.write(json.dumps(snapshot()) + '\n'); stream.flush()
                if stop.wait(5): break

    def command(name, args):
        print('Starting', name, flush=True)
        with (root / f'{name}.log').open('w') as log:
            subprocess.run(args, stdout=log, stderr=subprocess.STDOUT, check=True)
        print('Completed', name, flush=True)

    observer = threading.Thread(target=monitor)
    observer.start()
    try:
        for case, repeat in (('sum', 5), ('ray', 3)):
            command(f'timing-{case}', ['python3', 'benchmarks/raytrace-parallel/measure.py',
                str(root / f'{case}-manifest.json'), str(root / f'timing-{case}'),
                '--repeat', str(repeat), '--warmups', '1'])
        for lane in ('control4', 'candidate4'):
            command(f'profile-{lane}', ['python3', 'benchmarks/raytrace-thread-bottlenecks/profile.py',
                str(root / 'ray-manifest.json'), str(root / 'timing-ray/samples.json'),
                str(root / f'profile-{lane}'), '--lane', lane, '--duration', '3',
                '--interval-ms', '2', '--start-delay', '0.6'])
    finally:
        stop.set(); observer.join()
    subprocess.run(['python3', str(Path(__file__).with_name('timing_check.py')), str(root),
                    str(Path(__file__).with_name('timing-results.json'))], check=True)


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    run(Path(sys.argv[1]))
