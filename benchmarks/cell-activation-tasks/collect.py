#!/usr/bin/env python3
"""Collect saved Cell activation checks and work counters; no workload execution."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def report(root):
    result = read(root / 'report.json')
    keys = ['ordinal', 'ruleset', 'path', 'iterations', 'epoch', 'logical_matches', 'executed_bindings', 'changed']
    runs = [[s[k] for k in keys] for s in result['steps']]
    return {'runs': len(runs), 'state_sha256': sha(root / 'state.json'),
            'runs_sha256': hashlib.sha256(json.dumps(runs).encode()).hexdigest(),
            'report_sha256': sha(root / 'report.json'), 'query_workers': result['query_workers'],
            'key_lookup_calls': result['key_lookup_calls']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('before', type=Path)
    parser.add_argument('after', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    previous = read(args.before / 'checks/checks.json')
    checks = read(args.after / 'checks/checks.json')
    assert checks['baseline_commit'] == '00f33da0'
    assert previous['binaries']['candidate'] == checks['binaries']['baseline']
    assert checks['semantic_acceptance']['status'] == 'pass'
    result = {'scope': 'Standalone Cell CPU, short correctness/work checks; not speed or native egglog measurements',
              'baseline_commit': checks['baseline_commit'], 'binaries': checks['binaries'],
              'semantic_acceptance': checks['semantic_acceptance'], 'cases': {}, 'comparisons': {},
              'limits': 'Raytrace is a 128-Run prefix only. Grain 1 exercises coverage, not recommended speed. '
                        'Counters are uncalibrated operations, not cache misses or total allocation counts.'}
    for name, case in checks['cases'].items():
        result['cases'][name] = {'program_sha256': case['program_sha256'], 'lanes': {
            lane: {k: row[k] for k in ['runs', 'hashes', 'query_workers', 'key_lookup_calls', 'report_sha256']}
            for lane, row in case['lanes'].items()}}
    sources = {
        'sum': (args.before / 'checks/sum-four', args.after / 'checks/sum-four'),
        'fixture': (args.before / 'checks/fixture-four', args.after / 'checks/fixture-four'),
        'ray-prefix': (args.before / 'ray-prefix-after', args.after / 'ray-prefix-after'),
        'sum-g64': (args.after / 'sum-g64-before', args.after / 'sum-g64-after'),
    }
    for name, (old, new) in sources.items():
        a, b = report(old), report(new)
        for k in ['runs', 'state_sha256', 'runs_sha256', 'key_lookup_calls']:
            assert a[k] == b[k], (name, k)
        if name in ['sum', 'fixture']:
            assert a['report_sha256'] == previous['cases'][name]['lanes']['four']['report_sha256']
            assert b['report_sha256'] == checks['cases'][name]['lanes']['four']['report_sha256']
        if name == 'ray-prefix':
            assert a['runs'] == 128
        if name == 'sum-g64':
            assert a['state_sha256'] == checks['cases']['sum']['lanes']['four']['hashes']['state.json']
        for k in ['entries', 'answers', 'point_reads', 'steps', 'result_writes']:
            assert a['query_workers']['stats'][k] == b['query_workers']['stats'][k], (name, k)
        assert b['query_workers']['stats']['cell_order_comparisons'] == 0
        work = read(args.after / f'work-{name}.json')
        result['comparisons'][name] = {'before': a, 'after': b,
                                     'net_saved_operations': work['net_saved_operations']}
    result['raytrace_prefix_binaries'] = {'before': sha(args.before / 'query-prefix-final'),
                                         'after': sha(args.after / 'query-prefix-final')}
    # Both saved prefix runs use this frozen artifact. The hash is inherited
    # from the preceding iteration's recorded execution manifest.
    result['raytrace_prefix_program'] = read(args.before / 'prefix-manifest.json')['program_sha256']
    args.output.mkdir(exist_ok=True)
    for name in sources:
        shutil.copyfile(args.after / f'work-{name}.json', args.output / f'work-{name}.json')
    (args.output / 'results.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v['net_saved_operations'] for k, v in result['comparisons'].items()}))


if __name__ == '__main__':
    main()
