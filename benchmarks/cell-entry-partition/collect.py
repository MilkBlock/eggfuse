#!/usr/bin/env python3
"""Collect saved Cell/Seed partition checks; never execute workloads."""
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
    data = read(root / 'report.json')
    fields = ['ordinal', 'ruleset', 'path', 'iterations', 'epoch', 'logical_matches', 'executed_bindings', 'changed']
    runs = [[step[k] for k in fields] for step in data['steps']]
    return {'runs': len(runs), 'state_sha256': sha(root / 'state.json'),
            'runs_sha256': hashlib.sha256(json.dumps(runs).encode()).hexdigest(),
            'report_sha256': sha(root / 'report.json'), 'key_lookup_calls': data['key_lookup_calls'],
            'entry_schedule': data['entry_schedule'], 'query_workers': data['query_workers'],
            'spine': {k: data['stage_spine']['stats'][k] for k in [
                'routed_spine_seeds', 'routed_matcher_seeds', 'mixed_routed_queries', 'covered_by_rule']}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('before', type=Path)
    parser.add_argument('after', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    old_checks = read(args.before / 'checks/checks.json')
    checks = read(args.after / 'checks/checks.json')
    assert checks['baseline_commit'] == '7338103d'
    assert old_checks['binaries']['candidate'] == checks['binaries']['baseline']
    assert checks['semantic_acceptance']['status'] == 'pass'
    result = {'scope': 'Standalone Cell CPU; bounded correctness/work evidence, not timing or native runtime measurement',
              'baseline_commit': checks['baseline_commit'], 'binaries': checks['binaries'],
              'semantic_acceptance': checks['semantic_acceptance'], 'cases': {}, 'comparisons': {},
              'limits': 'One execution per short configuration, Raytrace prefix only. Entry layout sizes exclude allocator '
                        'capacity and referenced objects. Work scores charge the existing consumer_seed_deliveries counter '
                        'on both old and new reports; scores do not establish a speedup.'}
    for name, case in checks['cases'].items():
        result['cases'][name] = {'program_sha256': case['program_sha256'], 'lanes': {
            lane: {k: row[k] for k in ['runs', 'hashes', 'report_sha256', 'key_lookup_calls', 'query_workers']}
            for lane, row in case['lanes'].items()}}
    paths = {
        'sum': (args.before / 'checks/sum-four', args.after / 'checks/sum-four'),
        'fixture': (args.before / 'checks/fixture-four', args.after / 'checks/fixture-four'),
        'sum-g64': (args.before / 'sum-g64-after', args.after / 'sum-g64-after'),
        'ray-prefix': (args.before / 'ray-prefix-after', args.after / 'ray-prefix-after'),
        'extra': (args.after / 'checks/fixture-extra-baseline', args.after / 'checks/fixture-extra-four'),
    }
    for name, (before, after) in paths.items():
        a, b = report(before), report(after)
        for key in ['runs', 'state_sha256', 'runs_sha256', 'key_lookup_calls', 'spine']:
            assert a[key] == b[key], (name, key)
        old = a['entry_schedule']['stats']['consumer_seed_deliveries']
        new = b['entry_schedule']['stats']['consumer_seed_deliveries']
        direct = b['entry_schedule']['stats']['cell_entry_deliveries']
        assert old == new + direct and direct > 0, name
        if name in ['sum', 'fixture']:
            assert a['report_sha256'] == old_checks['cases'][name]['lanes']['four']['report_sha256']
        if name == 'ray-prefix':
            assert a['runs'] == 128
        if name == 'sum-g64':
            assert b['state_sha256'] == checks['cases']['sum']['lanes']['four']['hashes']['state.json']
        result['comparisons'][name] = {'before': a, 'after': b, 'seed_records_removed': direct}
        if name != 'extra':
            result['comparisons'][name]['net_saved_operations'] = read(args.after / f'work-{name}.json')['net_saved_operations']
    result['raytrace_prefix_binaries'] = {'before': sha(args.before / 'query-prefix-final'),
                                         'after': sha(args.after / 'query-prefix-final')}
    preceding = read(Path(__file__).parents[1] / 'cell-activation-tasks/results.json')
    assert preceding['raytrace_prefix_binaries']['after'] == result['raytrace_prefix_binaries']['before']
    result['raytrace_prefix_program'] = preceding['raytrace_prefix_program']
    args.output.mkdir(exist_ok=True)
    for name in ['sum', 'fixture', 'sum-g64', 'ray-prefix']:
        shutil.copyfile(args.after / f'work-{name}.json', args.output / f'work-{name}.json')
    (args.output / 'results.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({name: item['seed_records_removed'] for name, item in result['comparisons'].items()}))


if __name__ == '__main__':
    main()
