#!/usr/bin/env python3
"""Validate saved checks of the shared Cell column wiring; no workload runs."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def load(p):
    return json.loads(p.read_text())


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def work(value):
    if isinstance(value, dict):
        return {k: work(v) for k, v in value.items() if not k.endswith(('_seconds', '_ns'))}
    return [work(v) for v in value] if isinstance(value, list) else value


def check(root, commit, phase='links'):
    assert load(root / 'semantic-acceptance.json')['status'] == 'pass'
    a, b = [load(root / f'run-{lane}/report.json') for lane in ('baseline', 'candidate')]
    program = load(root / 'sum/program.json')
    assert all(r['status'] == 'complete' and r['program_sha256'] == program['sha256'] for r in (a, b))
    keys = ('ordinal', 'ruleset', 'path', 'iterations', 'epoch', 'logical_matches', 'executed_bindings', 'changed')
    runs = [[s[k] for k in keys] for s in a['steps']]
    assert runs == [[s[k] for k in keys] for s in b['steps']]
    assert sha(root / 'run-baseline/state.json') == sha(root / 'run-candidate/state.json')
    groups = ('stats', 'cell_ownership', 'stable_ports', 'free_join', 'sieve', 'neighbor_context', 'physical')
    if phase == 'query-frame':
        groups += ('local_context', 'stage_spine')
    for group in groups:
        assert work(a[group]) == work(b[group]), group
    metrics = []
    for lane in ('baseline', 'candidate'):
        data = load(root / f'metrics-{lane}.json')
        assert data['sources']['report']['sha256'] == sha(root / f'run-{lane}/report.json')
        assert data['sources']['program']['sha256'] == sha(root / 'sum/program.json')
        metrics.append({k: v for k, v in data['metrics'].items()
                        if not any(s in k for s in ('_seconds', '_ns ', '/phases/', 'peak_rss'))})
    assert metrics[0] == metrics[1]
    tests = {}
    test_names = (('context', 'cuts', 'free-join', 'entry') if phase == 'query-frame'
                  else ('final-unit', 'free-join', 'sieve', 'neighbor'))
    for name in test_names:
        p = root / f'test-{name}.log'
        passed = re.findall(r'test result: ok\. (\d+) passed; 0 failed;', p.read_text())
        assert sum(map(int, passed)) == 1
        tests[name] = {'passed': 1, 'log_sha256': sha(p)}
    p = root / ('test-minimal.log' if phase == 'query-frame' else 'test-final-minimal.log')
    assert 'Finished `dev` profile' in p.read_text()
    tests['minimal'] = {'status': 'pass', 'log_sha256': sha(p)}
    pairs = columns = 0
    for rule in program['recipe']['rules']:
        query = rule['query']
        for i, source in enumerate(query):
            if 'table' not in source['call']:
                continue
            slots = {arg['slot'] for arg in source['args'] if 'slot' in arg}
            for j, target in enumerate(query):
                if i == j or 'table' not in target['call']:
                    continue
                count = sum('slot' in arg and arg['slot'] in slots for arg in target['args'])
                pairs += int(count > 0)
                columns += count
    result = {'scope': 'standalone Cell CPU; normal release sum-bits; no new timing/allocation audit',
            'baseline_commit': '7f4e24c2' if phase == 'query-frame' else '78836033',
            'candidate_commit': commit, 'semantic_acceptance': 'pass',
            'runs': len(runs), 'state_sha256': sha(root / 'run-candidate/state.json'),
            'program_file_sha256': sha(root / 'sum/program.json'),
            'unchanged_work_metric_values_or_missing_status': len(metrics[0]),
            'unchanged_report_groups': groups,
            'static_source_wiring': {'directed_atom_pairs': pairs, 'column_links': columns,
                                    'scope': 'computed from typed recipe, not executed matches or mutations'},
            'free_join': b['free_join'], 'sieve_stats': {k: v for k, v in b['sieve']['stats'].items() if k != 'per_rule'},
            'tests': tests, 'binaries': {lane: sha(root / f'runtime-{lane}') for lane in ('baseline', 'candidate')},
            'timing_cadence': {'last_timed_commit': 'ab33d47c', 'implementation_commits_since_timing': 3},
            'limits': 'Common static wiring removes duplicate preparation; filters and live indexes remain necessary. No speedup or full B2/B3 takeover claimed; prior timing regression remains unresolved.'}
    if phase == 'query-frame':
        result['timing_cadence'] = {'last_timed_commit': '7f4e24c2', 'implementation_commits_since_timing': 1}
        result['local_context'] = b['local_context']
        result['limits'] = ('One Cell binder replaces four separate comparison/assignment implementations. '
            'Storage lifetime, trails, complete compiled-query fields and context terminal projections remain distinct obligations. '
            'Unchanged counters do not prove full unification or speed preservation; previous timing regression remains unresolved.')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--phase', choices=('links', 'query-frame'), default='links')
    args = parser.parse_args()
    args.output.write_text(json.dumps(check(args.root, args.commit, args.phase), indent=2) + '\n')
