#!/usr/bin/env python3
"""Keep checkpoint timing samples and semantic signatures without raw reports."""
import hashlib
import json
from pathlib import Path
import statistics
import sys


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def summarize(root, output):
    result = {'scope': 'standalone Cell CPU; normal binaries; process CPU includes setup/export',
              'implementation_commit': '356f0424', 'control_commit': '8369a224',
              'inference_only_utilization': 'not measured', 'workloads': {}}
    for case in ('sum', 'ray'):
        path = root / case / 'samples.json'
        raw = json.loads(path.read_text())
        assert raw.get('finished_at_utc')
        lanes = {}
        for name, lane in raw['lanes'].items():
            fields = ('iteration', 'process_wall_seconds', 'inference_seconds',
                      'process_user_seconds', 'process_system_seconds', 'load_seconds',
                      'setup_seconds', 'export_seconds', 'report_seconds', 'runs',
                      'state_sha256', 'schedule_sha256', 'phases', 'key_lookup_calls')
            samples = [{k: s[k] for k in fields if k in s} for s in lane['samples']]
            assert len(samples) == raw['repeat']
            cpu = [(s['process_user_seconds'] + s['process_system_seconds']) / s['process_wall_seconds'] for s in samples]
            phases = samples[0]['phases']
            lanes[name] = {'args': lane['args'], 'runtime_sha256': lane['runtime_sha256'],
                           'program_file_sha256': lane['program_file_sha256'], 'samples': samples,
                           'medians': lane['medians'], 'median_process_cpu_to_wall': statistics.median(cpu),
                           'median_phases': {k: statistics.median(s['phases'][k] for s in samples) for k in phases}}
        result['workloads'][case] = {
            'raw_samples_sha256': sha(path), 'repeat': raw['repeat'], 'warmups': raw['warmups'],
            'started_at_utc': raw['started_at_utc'], 'finished_at_utc': raw['finished_at_utc'],
            'execution_order': raw['execution_order'], 'semantic_reference': raw['semantic_reference'],
            'lanes': lanes,
        }
    output.write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    summarize(*map(Path, sys.argv[1:]))
