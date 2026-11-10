#!/usr/bin/env python3
"""Collect a whole-branch merge regression check without executing workloads."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import shutil


def read(path):
    return json.loads(path.read_text())


def save(path, data):
    path.write_text(json.dumps(data, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.mkdir(exist_ok=True)
    checks = read(args.root / 'checks/checks.json')
    provenance = read(args.root / 'provenance.json')
    assert checks['baseline_commit'] == provenance['before'][:8]
    assert checks['binaries'] == dict(baseline=provenance['binaries']['before'],
                                      candidate=provenance['binaries']['after'])
    assert checks['semantic_acceptance']['status'] == 'pass'
    helpers = runpy.run_path(str(Path(__file__).parents[1] / 'raytrace-parallel/collect.py'))
    dist, ratio = helpers['distribution'], helpers['paired_ratio']
    result = {'scope': provenance['scope'], 'provenance': provenance,
              'semantic_acceptance': checks['semantic_acceptance'], 'checks': {}, 'workloads': {},
              'limits': 'Small interleaved sample on an interactive machine. Frozen catalogs isolate '
                        'merge overhead. Same final graphs and ordered Run signatures are regression '
                        'evidence, not an independent native Raytrace proof. No new worker RHS execution.'}
    for name, case in checks['cases'].items():
        reference = case['lanes']['baseline']['hashes']
        assert all(row['hashes'] == reference for row in case['lanes'].values())
        result['checks'][name] = {'program_sha256': case['program_sha256'], 'lanes': {
            label: {k: row[k] for k in ['runs', 'hashes', 'report_sha256', 'key_lookup_calls']}
            for label, row in case['lanes'].items()}}
    for workload, runs in [('sum', 1428), ('ray', 16883)]:
        raw_path = args.root / f'{workload}-timing/samples.json'
        source = read(raw_path)
        assert source.get('finished_at_utc') and 'failure' not in source
        compact = {k: source[k] for k in ['scope', 'repeat', 'warmups', 'started_at_utc',
                   'finished_at_utc', 'execution_order', 'semantic_reference']}
        compact['raw_samples_sha256'] = hashlib.sha256(raw_path.read_bytes()).hexdigest()
        compact['lanes'] = {}
        summary = {'repeat': source['repeat'], 'warmups': source['warmups'],
                   'semantic_reference': source['semantic_reference'], 'lanes': {}, 'comparisons': {}}
        for name, lane in source['lanes'].items():
            rows = sorted(lane['samples'], key=lambda r: r['iteration'])
            assert [r['iteration'] for r in rows] == list(range(source['repeat']))
            if name.startswith(('before_', 'after_')):
                assert lane['runtime_sha256'] == provenance['binaries'][name.split('_')[0]]
            for row in [*lane['warmup_samples'], *rows]:
                assert row['runs'] == runs
                assert {k: row[k] for k in source['semantic_reference']} == source['semantic_reference']
                worker = row.get('query_workers') or {'enabled': False}
                if worker['enabled']:
                    s = worker['stats']
                    assert s['entries'] == sum(s['worker_entries']) + s['coordinator_entries']
            fields = ['iteration', 'inference_seconds', 'process_wall_seconds', 'process_user_seconds',
                      'process_system_seconds', 'setup_seconds', 'load_seconds', 'report_seconds',
                      'export_seconds', 'peak_rss_through_inference_bytes', 'phases', 'key_lookup_calls',
                      'runs', 'state_sha256', 'schedule_sha256']
            compact['lanes'][name] = {k: lane[k] for k in ['args', 'runtime_sha256', 'program_file_sha256']}
            compact['lanes'][name].update({k: [{f: r[f] for f in fields} for r in lane[k]]
                                          for k in ['warmup_samples', 'samples']})
            summary['lanes'][name] = {
                'timing': {k: dist([r[k] for r in rows]) for k in ['inference_seconds',
                    'process_wall_seconds', 'setup_seconds', 'peak_rss_through_inference_bytes']},
                'phases': {k: dist([r['phases'][k] for r in rows]) for k in rows[0]['phases']},
                'average_process_cores': [(r['process_user_seconds'] + r['process_system_seconds']) /
                                          r['process_wall_seconds'] for r in rows],
                'query_workers_first_sample': rows[0]['query_workers']}
        pairs = [(f'before_{mode}', f'after_{mode}') for mode in ['serial', 'inline1', 'query4']]
        pairs += [('after_inline1', 'after_query4')]
        if 'historical_serial' in source['lanes']:
            pairs += [('historical_serial', 'after_query4')]
        for before, after in pairs:
            a, b = [sorted(source['lanes'][n]['samples'], key=lambda r: r['iteration'])
                    for n in [before, after]]
            summary['comparisons'][f'{after}/{before}'] = {
                k: ratio([r[k] for r in a], [r[k] for r in b])
                for k in ['inference_seconds', 'process_wall_seconds']}
        result['workloads'][workload] = summary
        save(args.output / f'{workload}-samples.json', compact)
        shutil.copyfile(args.root / f'{workload}-manifest.json', args.output / f'{workload}-manifest.json')
    save(args.output / 'results.json', result)
    print(json.dumps({w: {n: v['timing']['inference_seconds']['median'] for n, v in s['lanes'].items()}
                      for w, s in result['workloads'].items()}, indent=2))


if __name__ == '__main__':
    main()
