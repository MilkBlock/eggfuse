#!/usr/bin/env python3
"""Collect bounded Cell scratch/completion evidence; never run a benchmark."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('before', type=Path)
    parser.add_argument('after', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    previous = read(args.before / 'final/checks.json')
    checks = read(args.after / 'checks/checks.json')
    assert checks['baseline_commit'] == 'ae123cf9'
    assert previous['binaries']['candidate'] == checks['binaries']['baseline']
    assert checks['semantic_acceptance']['status'] == 'pass'
    result = {
        'scope': 'Standalone Cell CPU, bounded semantic/work checks; not speed or native egglog measurements',
        'baseline_commit': checks['baseline_commit'], 'binaries': checks['binaries'],
        'semantic_acceptance': checks['semantic_acceptance'], 'cases': {}, 'work_comparisons': {},
        'limits': 'One execution per short configuration. Scratch growth depends on worker assignment. '
                  'Raytrace is only a 128-Run prefix; no full workload timing in this iteration. '
                  'Buffer counters are neither all allocations nor hardware cache misses.',
    }
    for name, case in checks['cases'].items():
        result['cases'][name] = {'program_sha256': case['program_sha256'], 'lanes': {
            lane: {key: row[key] for key in ['runs', 'hashes', 'query_workers', 'key_lookup_calls', 'report_sha256']}
            for lane, row in case['lanes'].items()}}
    # Reuse the saved previous release's worker executions. Verify that the
    # comparison is against that binary/report, not the serial reference lane.
    for name in ['sum', 'fixture']:
        reports = []
        for root, recorded in [(args.before / 'final', previous), (args.after / 'checks', checks)]:
            path = root / f'{name}-four/report.json'
            evidence = recorded['cases'][name]['lanes']['four']
            assert sha(path) == evidence['report_sha256']
            report = read(path)
            assert report['query_workers']['workers'] == 4
            reports.append(report)
        before, after = reports
        for field in ['key_lookup_calls', 'fact_decode_calls', 'fact_decode_ports']:
            assert before[field] == after[field]
        for field in ['entries', 'answers', 'steps', 'point_reads', 'result_writes', 'cell_order_comparisons']:
            assert before['query_workers']['stats'][field] == after['query_workers']['stats'][field]
        assert after['query_workers']['stats']['completion_slot_initializations'] == 0
        assert after['query_workers']['stats']['completion_slot_writes'] == 0
        result['work_comparisons'][name] = {
            'before': before['query_workers'], 'after': after['query_workers'],
            'ledger': f'work-{name}.json',
        }
    keys = ['ordinal', 'ruleset', 'path', 'iterations', 'epoch', 'logical_matches', 'executed_bindings', 'changed']
    signatures = []
    prefix = {}
    for lane in ['before', 'after']:
        root = args.after / f'ray-prefix-{lane}'
        report = read(root / 'report.json')
        runs = [[step[k] for k in keys] for step in report['steps']]
        assert len(runs) == 128
        signature = {'state': sha(root / 'state.json'), 'runs': hashlib.sha256(json.dumps(runs).encode()).hexdigest()}
        signatures.append(signature)
        prefix[lane] = {'hashes': signature, 'report_sha256': sha(root / 'report.json'),
                        'runs': len(runs), 'query_workers': report['query_workers'],
                        'key_lookup_calls': report['key_lookup_calls']}
    assert signatures[0] == signatures[1]
    assert prefix['before']['key_lookup_calls'] == prefix['after']['key_lookup_calls']
    result['raytrace_prefix'] = prefix
    manifest = read(args.after / 'prefix-manifest.json')
    assert (manifest['runs'], manifest['workers'], manifest['grain']) == (128, 4, 64)
    assert manifest['binaries']['before'] == sha(args.before / 'query-prefix-final')
    assert manifest['binaries']['after'] == sha(args.after / 'query-prefix-final')
    result['raytrace_prefix_manifest'] = manifest
    args.output.mkdir(exist_ok=True)
    for name in ['sum', 'fixture', 'ray-prefix']:
        shutil.copyfile(args.after / f'work-{name}.json', args.output / f'work-{name}.json')
    (args.output / 'results.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({name: read(args.output / f'work-{name}.json')['net_saved_operations']
                      for name in ['sum', 'fixture', 'ray-prefix']}))


if __name__ == '__main__':
    main()
