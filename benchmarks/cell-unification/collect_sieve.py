#!/usr/bin/env python3
"""Check borrowed Sieve wiring and the five-commit timing checkpoint from saved artifacts."""
import argparse
import json
from pathlib import Path
import re
import runpy

from check_links import load, sha, work

REPO = Path(__file__).resolve().parents[2]
TIMING = runpy.run_path(str(REPO / 'benchmarks/raytrace-parallel/collect.py'))
RUN_KEYS = ('ordinal', 'ruleset', 'path', 'iterations', 'epoch', 'logical_matches',
            'executed_bindings', 'changed')


def collect(root, commit, timed):
    assert load(root / 'semantic-acceptance.json')['status'] == 'pass'
    program = root / 'sum/program.json'
    a, b = [load(root / f'run-{lane}/report.json') for lane in ('baseline', 'candidate')]
    assert all(r['status'] == 'complete' and r['program_sha256'] == load(program)['sha256']
               for r in (a, b))
    runs = [[s[k] for k in RUN_KEYS] for s in a['steps']]
    assert runs == [[s[k] for k in RUN_KEYS] for s in b['steps']]
    assert sha(root / 'run-baseline/state.json') == sha(root / 'run-candidate/state.json')
    groups = ('stats', 'cell_ownership', 'stable_ports', 'free_join', 'sieve',
              'neighbor_context', 'physical', 'stage_spine')
    for group in groups:
        assert work(a[group]) == work(b[group]), group
    metrics = []
    for lane in ('baseline', 'candidate'):
        data = load(root / f'metrics-{lane}.json')
        assert data['sources']['report']['sha256'] == sha(root / f'run-{lane}/report.json')
        assert data['sources']['program']['sha256'] == sha(program)
        metrics.append({k: v for k, v in data['metrics'].items()
                        if not any(s in k for s in ('_seconds', '_ns ', '/phases/', 'peak_rss'))})
    assert metrics[0] == metrics[1]
    tests = {}
    for name, expected in (('unit', 2), ('bridge', 1), ('free-join', 1)):
        p = root / f'test-{name}.log'
        passed = re.findall(r'test result: ok\. (\d+) passed; 0 failed;', p.read_text())
        assert sum(map(int, passed)) == expected, name
        tests[name] = {'passed': expected, 'log_sha256': sha(p)}
    p = root / 'test-minimal.log'
    assert 'Finished `dev` profile' in p.read_text()
    tests['minimal'] = {'status': 'pass', 'log_sha256': sha(p)}
    result = {
        'scope': 'standalone Cell CPU; normal release; not native egglog timing',
        'features': 'sparse-cells,view-ports,storage-metrics',
        'baseline_runtime_commit': '563e4ab0', 'baseline_source_commit': '6dd18b55',
        'candidate_commit': commit, 'semantic_acceptance': 'pass', 'runs': len(runs),
        'state_sha256': sha(root / 'run-candidate/state.json'),
        'program_file_sha256': sha(program), 'unchanged_report_groups': groups,
        'unchanged_work_metric_values_or_missing_status': len(metrics[0]), 'tests': tests,
        'sieve_stats': {k: v for k, v in b['sieve']['stats'].items() if k != 'per_rule'},
        'removed_spec_clones': {'successful_builds': b['sieve']['stats']['builds'],
            'basis': 'One removed Spec clone per completed build in the old source; inferred from build count, not allocator instrumentation. Nested rule-target clones also removed but not counted.'},
        'binaries': {lane: sha(root / f'runtime-{lane}') for lane in ('baseline', 'candidate')},
        'allocation_status': 'not collected; removed source clones are not measured allocation savings',
    }
    if timed:
        result['timing'] = timing(root, commit)
        result['performance_status'] = 'speedup_not_established_preservation_unresolved'
        result['timing_cadence'] = {'last_timed_commit': commit,
            'implementation_commits_since_timing': 0,
            'implementation_commits_in_batch': ['50e12acf', '78836033', '563e4ab0', '6dd18b55', commit]}
    result['limits'] = ('Focused semantic/work checks and at most one short sum-bits timing campaign. '
        'No Raytrace, full multithread or whole Cell unification acceptance. '
        'Unchanged work counters do not prove speed preservation; prior regression remains under review.')
    return result


def timing(root, commit, commits=None):
    path = root / 'timing/samples.json'
    data = load(path)
    assert data.get('finished_at_utc') and 'failure' not in data
    assert data['repeat'] == 7 and data['warmups'] == 1
    commits = commits or {'baseline': '563e4ab0', 'candidate': commit,
               'last_timed': 'ab33d47c', 'historical': '24c4ae8a'}
    fields = ('inference_seconds', 'process_wall_seconds', 'load_seconds', 'setup_seconds',
              'export_seconds', 'report_seconds', 'process_after_report_residual_seconds',
              'peak_rss_through_inference_bytes')
    result = {'source_sha256': sha(path), 'repeat': 7, 'warmups': 1,
              'started_at_utc': data['started_at_utc'], 'finished_at_utc': data['finished_at_utc'],
              'execution_order': data['execution_order'], 'lanes': {}, 'comparisons': {}}
    rows = {}
    assert set(data['lanes']) == set(commits)
    for lane, values in data['lanes'].items():
        assert values['runtime_sha256'] == sha(root / f'runtime-{lane}')
        assert values['program_file_sha256'] == sha(root / 'sum/program.json')
        rows[lane] = sorted(values['samples'], key=lambda r: r['iteration'])
        assert [r['iteration'] for r in rows[lane]] == list(range(7))
        assert all(all(r[k] == v for k, v in data['semantic_reference'].items()) for r in rows[lane])
        result['lanes'][lane] = {'commit': commits[lane], 'runtime_sha256': values['runtime_sha256'],
            'timing': {f: TIMING['distribution']([r[f] for r in rows[lane]]) for f in fields},
            'samples': [{f: r[f] for f in ('iteration',) + fields} for r in rows[lane]]}
    for lane in ('baseline', 'last_timed', 'historical'):
        result['comparisons'][f'candidate/{lane}'] = {
            f: TIMING['paired_ratio']([r[f] for r in rows[lane]], [r[f] for r in rows['candidate']])
            for f in ('inference_seconds', 'process_wall_seconds')}
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--commit', required=True)
    p.add_argument('--timing', action='store_true')
    args = p.parse_args()
    args.output.write_text(json.dumps(collect(args.root, args.commit, args.timing), indent=2) + '\n')
