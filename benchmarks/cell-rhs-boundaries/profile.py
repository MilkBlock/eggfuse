#!/usr/bin/env python3
"""Sample a frozen Cell runtime separately from timing; check its full execution."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import threading
import time

BENCHMARKS = Path(__file__).resolve().parents[1]
check = runpy.run_path(str(BENCHMARKS / 'cell-bake-full-merge/check.py'))
sha, read = check['sha'], check['read']
KEYS = runpy.run_path(str(BENCHMARKS / 'raytrace-parallel/measure.py'))['KEYS']


def collect(reference, output, delay, duration):
    jobs = runpy.run_path(str(BENCHMARKS.parent / 'tools/local_jobs.py'))
    if jobs['current_lease']() is None:
        raise RuntimeError('Launch this diagnostic through eggfuse-job run --kind compute')
    manifest = read(reference / 'manifest.json')
    config = manifest['lanes']['ray']
    runtime = reference / 'candidate-runtime'
    original = read(reference / 'candidate-ray/report.json')
    assert sha(runtime) == manifest['runtime_sha256']
    assert original['status'] == 'complete'
    output.mkdir()
    command = [str(runtime.resolve()), '--program', config['program'], '--output', str((output / 'runtime').resolve()), *config['args']]
    env = dict(os.environ)
    env.pop('CELL_CPU_PROGRESS', None)
    env.pop('CELL_CPU_PROFILE', None)
    with (output / 'runtime.log').open('w') as log:
        process = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT)
        watchdog = threading.Timer(120, process.kill)
        watchdog.start()
        try:
            time.sleep(delay)
            if process.poll() is not None:
                raise RuntimeError('Runtime exited before diagnostic sampling began')
            sample = ['/usr/bin/sample', str(process.pid), str(duration), '2', '-mayDie', '-file', str((output / 'stacks.txt').resolve())]
            with (output / 'sample.log').open('w') as sample_log:
                sampled = subprocess.run(sample, stdout=sample_log, stderr=subprocess.STDOUT, timeout=duration + 30)
            process.wait()
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
            watchdog.cancel()
            watchdog.join()
    assert process.returncode == 0 and sampled.returncode == 0
    report = read(output / 'runtime/report.json')
    assert report['status'] == 'complete' and report['program_sha256'] == original['program_sha256']
    assert sha(output / 'runtime/state.json') == sha(reference / 'candidate-ray/state.json')
    schedule = [[s[k] for k in KEYS] for s in report['steps']]
    assert schedule == [[s[k] for k in KEYS] for s in original['steps']]
    effects = ('bindings', 'constructor_requests', 'constructor_reused', 'logical_facts_created',
               'function_updates', 'union_requests', 'unions', 'merge_calls')
    assert all(report['stats'][k] == original['stats'][k] for k in effects)
    threads = runpy.run_path(str(BENCHMARKS / 'raytrace-thread-bottlenecks/collect.py'))['sample_threads'](output / 'stacks.txt')
    assert any('execute_until' in symbol for symbol in threads[0]['inclusive']), 'sample did not establish inference coverage'
    result = dict(scope='actual standalone Cell runtime; sampled diagnostic, not performance acceptance',
        reference_commit=manifest['control_commit'], runtime_sha256=sha(runtime), program_sha256=report['program_sha256'],
        state_sha256=sha(output / 'runtime/state.json'),
        schedule_sha256=hashlib.sha256(json.dumps(schedule,separators=(',', ':')).encode()).hexdigest(),
        exact_state_runs_effects=True, sample_delay_seconds=delay, sample_duration_seconds=duration,
        sample_interval_ms=2, sample_sha256=sha(output / 'stacks.txt'),
        phases={k:sum(s['phases'][k] for s in report['steps']) for k in report['steps'][0]['phases']},
        threads=threads,
        limits='A bounded wall-residence sample, not CPU percentages or a full-run census. Inclusive stacks overlap; inlining limits attribution. No per-Run logging or query profiling was enabled.')
    (output / 'profile.json').write_text(json.dumps(result, indent=2) + '\n')
    state = output / 'runtime/state.json'
    with state.open('rb') as source, gzip.open(str(state)+'.gz', 'wb', compresslevel=1) as compressed:
        shutil.copyfileobj(source, compressed)
    state.unlink()
    for thread in threads:
        print(thread['thread'], 'samples', thread['samples'])
        print(list(thread['own'].items())[:12])


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('Run without Python -O')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--delay', type=float, default=1.0)
    parser.add_argument('--duration', type=int, default=2)
    args = parser.parse_args()
    collect(args.reference.resolve(), args.output.resolve(), args.delay, args.duration)
