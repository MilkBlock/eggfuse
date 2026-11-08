#!/usr/bin/env python3
"""Interleave fresh processes and compare graph + semantic schedule every run.

SPEC: {case: {lane: {runtime: PATH, program: PATH, args?: [FLAG]}}}.
One warmup per lane.
Large generated exports are removed only after a verified summary is saved.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import statistics
import subprocess

KEYS = ('ordinal', 'ruleset', 'path', 'iterations', 'epoch', 'logical_matches', 'executed_bindings', 'changed')


def sha(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def save(path, value):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, indent=2) + '\n')
    tmp.replace(path)


def measure(spec, output, repeat):
    output.mkdir()
    result = {'repeat': repeat, 'warmups': 1, 'scope': 'standalone Cell CPU; inference excludes setup and export', 'cases': {}}
    for case, lanes in spec.items():
        rows = {label: dict(runtime_sha256=sha(v['runtime']), program_file_sha256=sha(v['program']), args=v.get('args', []), samples=[])
                for label, v in lanes.items()}
        result['cases'][case] = rows
        reference = None
        rng = random.Random(20261108)
        for iteration in range(-1, repeat):
            order = list(lanes)
            rng.shuffle(order)
            for label in order:
                config = lanes[label]
                directory = output / f'{case}-{label}-{iteration}'
                with (output / f'{directory.name}.log').open('w') as log:
                    subprocess.run([config['runtime'], '--program', config['program'], '--output', str(directory), *config.get('args', [])],
                                   stdout=log, stderr=subprocess.STDOUT, check=True)
                report = json.loads((directory / 'report.json').read_text())
                assert report['status'] == 'complete'
                schedule = [[s[k] for k in KEYS] for s in report['steps']]
                stamp = [sha(directory / 'state.json'), hashlib.sha256(json.dumps(schedule, separators=(',', ':')).encode()).hexdigest()]
                if reference is None:
                    reference = stamp
                assert stamp == reference, (case, label, iteration, stamp, reference)
                record = {k: report[k] for k in ('setup_seconds', 'inference_seconds', 'export_seconds',
                    'peak_rss_through_inference_bytes', 'stats')}
                record.update(iteration=iteration, state_file_sha256=stamp[0], schedule_sha256=stamp[1],
                              stage_spine=report['stage_spine']['stats'])
                record['phases'] = {k: sum(s['phases'][k] for s in report['steps'])
                                    for k in report['steps'][0]['phases']}
                record['repair_ports'] = report.get('repair_ports', {}).get('stats')
                record['entry_schedule'] = report['entry_schedule']
                record['publication'] = report['publication']
                record['key_lookup_calls'] = report['key_lookup_calls']
                if iteration < 0:
                    rows[label]['warmup'] = record
                else:
                    rows[label]['samples'].append(record)
                save(output / 'samples.json', result)
                (directory / 'state.json').unlink()
                (directory / 'report.json').unlink()
                directory.rmdir()
                print(case, label, iteration, report['inference_seconds'], flush=True)
        for row in rows.values():
            row['median_inference_seconds'] = statistics.median(s['inference_seconds'] for s in row['samples'])
            row['median_peak_rss_bytes'] = statistics.median(s['peak_rss_through_inference_bytes'] for s in row['samples'])
        save(output / 'samples.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('spec', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--repeat', type=int, default=7)
    args = parser.parse_args()
    assert args.repeat > 0
    measure(json.loads(args.spec.read_text()), args.output, args.repeat)
