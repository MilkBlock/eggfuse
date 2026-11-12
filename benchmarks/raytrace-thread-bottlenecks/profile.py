#!/usr/bin/env python3
"""Sample a separate macOS diagnostic process; never include it in timing samples."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import threading
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('reference', type=Path, help='Completed timing samples.json')
    parser.add_argument('output', type=Path)
    parser.add_argument('--lane', default='overlap4')
    parser.add_argument('--duration', type=int, default=10)
    parser.add_argument('--interval-ms', type=int, default=5)
    parser.add_argument('--start-delay', type=float, help='Sample after this launch delay with progress logging disabled; validate inference coverage from the resulting stack tree')
    args = parser.parse_args()
    if args.start_delay is not None and args.start_delay < 0:
        parser.error('--start-delay must be nonnegative')
    base = runpy.run_path(str(Path(__file__).parents[1] / 'raytrace-parallel/measure.py'))
    config = json.loads(args.manifest.read_text())['lanes'][args.lane]
    reference = json.loads(args.reference.read_text())
    assert reference.get('finished_at_utc') and 'failure' not in reference
    lane = reference['lanes'][args.lane]
    assert base['sha'](config['runtime']) == lane['runtime_sha256']
    assert base['sha'](config['program']) == lane['program_file_sha256']
    args.output.mkdir()
    runtime_output = args.output / 'runtime'
    log_path = args.output / 'runtime.log'
    command = [str(Path(config['runtime']).resolve()), '--program',
               str(Path(config['program']).resolve()), '--output', str(runtime_output.resolve()),
               *config.get('args', [])]
    env = dict(os.environ, **config.get('environment', {}))
    if args.start_delay is None:
        env['CELL_CPU_PROGRESS'] = '1'
    else:
        env.pop('CELL_CPU_PROGRESS', None)
    start = time.monotonic()
    with log_path.open('w') as log:
        process = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT)
        watchdog = threading.Timer(90, process.kill)
        watchdog.start()
        try:
            if args.start_delay is None:
                # Exact inference trigger; each Run's logging perturbs this lane.
                while '[cell-cpu] Run ' not in log_path.read_text():
                    if process.poll() is not None:
                        raise RuntimeError(f'Exited before inference: {process.returncode}; {log_path}')
                    time.sleep(0.02)
            else:
                # The caller calibrates this delay from saved startup measurements.
                # Stacks must establish actual inference coverage; this is no proof.
                time.sleep(args.start_delay)
                if process.poll() is not None:
                    raise RuntimeError('Process exited before delayed sample')
            trigger_seconds = time.monotonic() - start
            command_sample = ['/usr/bin/sample', str(process.pid), str(args.duration),
                              str(args.interval_ms), '-mayDie', '-file',
                              str((args.output / 'stacks.txt').resolve())]
            with (args.output / 'sample.log').open('w') as sample_log:
                sampled = subprocess.run(command_sample, stdout=sample_log,
                                         stderr=subprocess.STDOUT, timeout=args.duration + 30)
            sample_end_seconds = time.monotonic() - start
            process.wait()
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
            watchdog.cancel()
            watchdog.join()
    assert process.returncode == 0, (process.returncode, log_path)
    assert sampled.returncode == 0, sampled.returncode
    report = json.loads((runtime_output / 'report.json').read_text())
    assert report['status'] == 'complete'
    schedule = [[s[k] for k in base['KEYS']] for s in report['steps']]
    stamp = {'state_sha256': base['sha'](runtime_output / 'state.json'),
             'schedule_sha256': hashlib.sha256(json.dumps(schedule, separators=(',', ':')).encode()).hexdigest()}
    assert stamp == reference['semantic_reference'], stamp
    phases = {k: sum(s['phases'][k] for s in report['steps']) for k in report['steps'][0]['phases']}
    summary = {
        'scope': 'Standalone Cell CPU, separate instrumented diagnostic; not a timing sample or native egglog',
        'lane': args.lane, 'args': config['args'], 'runs': len(schedule), **stamp,
        'runtime_sha256': lane['runtime_sha256'], 'program_file_sha256': lane['program_file_sha256'],
        'sample': {'command': command_sample, 'trigger': ('first source Run in progress log' if args.start_delay is None else 'fixed launch delay, progress disabled'),
                   'start_delay_seconds': args.start_delay, 'progress_logging': args.start_delay is None,
                   'trigger_seconds_since_launch': trigger_seconds,
                   'command_end_seconds_since_launch': sample_end_seconds,
                   'stacks_sha256': base['sha'](args.output / 'stacks.txt'),
                   'limits': 'Sampling includes wall-time residence on parked threads; stack counts are not CPU percentages. Symbolication time is included in command end. Sampling perturbs this diagnostic; see progress_logging for whether per-Run logging is enabled.'},
        'inference_seconds_diagnostic_only': report['inference_seconds'], 'phases': phases,
        'stats': report['stats'], 'stable_ports': report.get('stable_ports'),
        'cell_ownership': report.get('cell_ownership'), 'key_lookup_calls': report.get('key_lookup_calls')}
    (args.output / 'diagnostic.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({'runs': len(schedule), 'phases': phases, 'sample': summary['sample']}, indent=2))


if __name__ == '__main__':
    main()
