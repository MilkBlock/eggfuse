#!/usr/bin/env python3
"""Measure fresh Raytrace processes, with semantic and worker-work checks."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import random
import resource
import statistics
import subprocess
import threading
import time

KEYS = ('ordinal', 'ruleset', 'path', 'iterations', 'epoch', 'logical_matches', 'executed_bindings', 'changed')


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def save(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def run_process(command, env, log, timeout):
    # subprocess.run(timeout=...) polls waitpid with sleeps up to 50 ms on
    # POSIX. That quantizes short whole-process timings. Block in waitpid and
    # enforce the limit from a watchdog instead.
    process = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT)
    expired = threading.Event()

    def expire():
        if process.poll() is None:
            expired.set()
            process.kill()

    timer = threading.Timer(timeout, expire)
    timer.start()
    try:
        process.wait()
    finally:
        timer.cancel()
        timer.join()
    if expired.is_set():
        raise subprocess.TimeoutExpired(command, timeout)
    return process


def measure(spec, output, repeat, warmups, timeout):
    output.mkdir()
    (output / 'binaries').mkdir()
    (output / 'inputs').mkdir()
    lanes = spec['lanes']
    execution = {}
    result = {'scope': 'standalone Cell CPU; real process wall and inference timing; not native egglog',
              'repeat': repeat, 'warmups': warmups, 'seed': 20261109,
              'started_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'path_policy': 'equal-length executable/input links and numeric output names',
              'process_wait': 'blocking waitpid with a separate timeout watchdog; no polling sleeps',
              'lanes': {}, 'execution_order': [], 'semantic_reference': None}
    for index, (label, config) in enumerate(lanes.items()):
        entry = dict(config)
        for key, folder in (('runtime', 'binaries'), ('program', 'inputs')):
            link = output / folder / f'{index:04d}'
            link.symlink_to(Path(config[key]).resolve())
            entry[key] = str(link.absolute())
        execution[label] = entry
        result['lanes'][label] = {'args': config.get('args', []), 'runtime_sha256': sha(config['runtime']),
                                  'program_file_sha256': sha(config['program']), 'samples': [], 'warmup_samples': [],
                                  'environment': config.get('environment', {})}
    rng = random.Random(result['seed'])
    env = dict(os.environ)
    env.pop('CELL_CPU_PROGRESS', None)
    for iteration in range(-warmups, repeat):
        order = list(lanes)
        rng.shuffle(order)
        if result['semantic_reference'] is None:
            first = next(iter(lanes))
            order.remove(first)
            order.insert(0, first)
        result['execution_order'].append({'iteration': iteration, 'lanes': order})
        for label in order:
            config = execution[label]
            directory = output / f'run-{iteration + warmups:04d}-{list(lanes).index(label):04d}'
            before_cpu = resource.getrusage(resource.RUSAGE_CHILDREN)
            with (output / f'{directory.name}.log').open('w') as log:
                start = time.perf_counter()
                try:
                    process = run_process([config['runtime'], '--program', config['program'],
                        '--output', str(directory.absolute()), *config.get('args', [])],
                        env=dict(env, **config.get('environment', {})), log=log, timeout=timeout)
                except subprocess.TimeoutExpired:
                    cpu = resource.getrusage(resource.RUSAGE_CHILDREN)
                    result['failure'] = {'lane': label, 'iteration': iteration,
                        'timeout_seconds': timeout, 'elapsed_seconds': time.perf_counter() - start,
                        'process_user_seconds': cpu.ru_utime - before_cpu.ru_utime,
                        'process_system_seconds': cpu.ru_stime - before_cpu.ru_stime,
                        'log': f'{directory.name}.log', 'state': 'child killed by watchdog and waited'}
                    save(output / 'samples.json', result)
                    raise
                elapsed = time.perf_counter() - start
            after_cpu = resource.getrusage(resource.RUSAGE_CHILDREN)
            if process.returncode:
                result['failure'] = {'lane': label, 'iteration': iteration, 'returncode': process.returncode,
                                     'log': f'{directory.name}.log'}
                save(output / 'samples.json', result)
                raise RuntimeError(result['failure'])
            report = json.loads((directory / 'report.json').read_text())
            assert report['status'] == 'complete', (label, report['status'])
            schedule = [[step[k] for k in KEYS] for step in report['steps']]
            stamp = {'state_sha256': sha(directory / 'state.json'),
                     'schedule_sha256': hashlib.sha256(json.dumps(schedule, separators=(',', ':')).encode()).hexdigest()}
            if result['semantic_reference'] is None:
                result['semantic_reference'] = stamp
            if stamp != result['semantic_reference']:
                result['failure'] = {'lane': label, 'iteration': iteration, 'semantic_difference': stamp}
                save(output / 'samples.json', result)
                raise RuntimeError(result['failure'])
            row = {'iteration': iteration, 'process_wall_seconds': elapsed, 'runs': len(schedule), **stamp,
                   'process_user_seconds': after_cpu.ru_utime - before_cpu.ru_utime,
                   'process_system_seconds': after_cpu.ru_stime - before_cpu.ru_stime}
            row.update({key: report[key] for key in ('load_seconds', 'setup_seconds', 'inference_seconds',
                        'export_seconds', 'peak_rss_through_inference_bytes') if key in report})
            row['phases'] = {key: sum(step['phases'][key] for step in report['steps'])
                             for key in report['steps'][0]['phases']}
            row['stats'] = report['stats']
            row['key_lookup_calls'] = report.get('key_lookup_calls')
            for key in ('scoped_executor', 'port_completion'):
                row[key] = report.get(key)
            stable = report.get('stable_ports', {})
            row['birth_absence_directory'] = stable.get('birth_absence_directory')
            row['parallel_guards'] = stable.get('parallel_guards')
            row['completion_batches'] = stable.get('completion_batches')
            for key in ('cell_ownership', 'stable_ports', 'maintenance'):
                row[key + '_stats'] = report.get(key, {}).get('stats') if isinstance(report.get(key), dict) else None
            target = 'warmup_samples' if iteration < 0 else 'samples'
            result['lanes'][label][target].append(row)
            save(output / 'samples.json', result)
            (directory / 'state.json').unlink()
            (directory / 'report.json').unlink()
            directory.rmdir()
            print(label, iteration, f'inference={row["inference_seconds"]:.6f}', f'wall={elapsed:.6f}', flush=True)
    result['finished_at_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    for lane in result['lanes'].values():
        if lane['samples']:
            lane['medians'] = {key: statistics.median(s[key] for s in lane['samples'])
                              for key in ('inference_seconds', 'process_wall_seconds', 'load_seconds',
                                          'setup_seconds', 'export_seconds', 'peak_rss_through_inference_bytes')
                              if all(key in s for s in lane['samples'])}
    save(output / 'samples.json', result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('spec', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--repeat', type=int, default=7)
    parser.add_argument('--warmups', type=int, default=1)
    parser.add_argument('--timeout', type=float, default=180)
    args = parser.parse_args()
    assert args.repeat >= 0 and args.warmups >= 0 and args.repeat + args.warmups > 0
    measure(json.loads(args.spec.read_text()), args.output, args.repeat, args.warmups, args.timeout)
