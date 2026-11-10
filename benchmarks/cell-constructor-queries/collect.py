#!/usr/bin/env python3
"""Collect constructor query and full-Raytrace evidence without running a workload."""
import argparse
import json
from pathlib import Path
import runpy
import shutil


def read(path):
    return json.loads(path.read_text())


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.mkdir(exist_ok=True)
    checks = read(args.root / 'final/checks.json')
    assert checks['baseline_commit'] == '5f87ba03'
    assert checks['semantic_acceptance']['status'] == 'pass'
    source = read(args.root / 'timing/samples.json')
    assert source.get('finished_at_utc') and 'failure' not in source
    helpers = runpy.run_path(str(Path(__file__).parents[1] / 'raytrace-parallel/collect.py'))
    distribution, ratio = helpers['distribution'], helpers['paired_ratio']
    result = {
        'scope': 'Standalone Cell CPU; borrowed constructor domains in source-Run Cell tasks; not native egglog',
        'baseline_commit': '5f87ba03',
        'historical_serial': 'efc06d49; saved f4fd21cb binary, runtime implementation 14e112c7',
        'repeat': source['repeat'], 'warmups': source['warmups'],
        'semantic_reference': source['semantic_reference'], 'lanes': {}, 'comparisons': {},
        'limits': 'Interactive Apple M3 Max, 16 logical CPU. Small interleaved sample; not hardware cache-miss measurement. No independent native Raytrace proof.',
    }
    for name, lane in source['lanes'].items():
        rows = sorted(lane['samples'], key=lambda row: row['iteration'])
        assert [row['iteration'] for row in rows] == list(range(source['repeat']))
        if name in ['current_serial', 'inline1', 'query4']:
            assert lane['runtime_sha256'] == checks['binaries']['candidate']
        if name == 'before_query4':
            assert lane['runtime_sha256'] == checks['binaries']['baseline']
        for row in [*lane['warmup_samples'], *rows]:
            assert row['runs'] == 16883
            assert {k: row[k] for k in source['semantic_reference']} == source['semantic_reference']
            q = row.get('query_workers') or {'enabled': False}
            if q['enabled']:
                s = q['stats']
                assert s['entries'] == sum(s['worker_entries']) + s.get('coordinator_entries', 0)
        result['lanes'][name] = {
            'runtime_sha256': lane['runtime_sha256'], 'program_sha256': lane['program_file_sha256'],
            'args': lane['args'],
            'timing': {k: distribution([row[k] for row in rows]) for k in [
                'inference_seconds', 'process_wall_seconds', 'setup_seconds', 'peak_rss_through_inference_bytes']},
            'phases': {k: distribution([row['phases'][k] for row in rows]) for k in rows[0]['phases']},
            'average_process_cores': [(r['process_user_seconds'] + r['process_system_seconds']) / r['process_wall_seconds'] for r in rows],
            'query_workers_first_sample': rows[0].get('query_workers'),
            'key_lookup_calls': rows[0]['key_lookup_calls'],
            'worker_entries': [(r.get('query_workers') or {}).get('stats', {}).get('worker_entries', []) for r in rows],
        }
    for base in ['historical_serial', 'before_query4', 'current_serial', 'inline1']:
        reference = sorted(source['lanes'][base]['samples'], key=lambda row: row['iteration'])
        result['comparisons'][base] = {}
        for name, lane in source['lanes'].items():
            rows = sorted(lane['samples'], key=lambda row: row['iteration'])
            result['comparisons'][base][name] = {k: ratio([r[k] for r in reference], [r[k] for r in rows])
                                              for k in ['inference_seconds', 'process_wall_seconds']}
    save(args.output / 'summary.json', result)
    compact = {'scope': checks['scope'], 'baseline_commit': checks['baseline_commit'],
               'binaries': checks['binaries'], 'semantic_acceptance': checks['semantic_acceptance'], 'cases': {}}
    for name, case in checks['cases'].items():
        compact['cases'][name] = {'program_sha256': case['program_sha256'], 'lanes': {
            label: {k: row[k] for k in ['runs', 'hashes', 'query_workers', 'key_lookup_calls', 'report_sha256']}
            for label, row in case['lanes'].items()}}
    save(args.output / 'checks.json', compact)
    for dest, path in [('samples.json', 'timing/samples.json'), ('manifest.json', 'timing-manifest.json'),
                       ('work-sum.json', 'work-sum.json')]:
        shutil.copyfile(args.root / path, args.output / dest)
    print(json.dumps({name: lane['timing']['inference_seconds']['median'] for name, lane in result['lanes'].items()}))


if __name__ == '__main__':
    main()
