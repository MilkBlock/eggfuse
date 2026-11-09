#!/usr/bin/env python3
"""Check saved producer-source rewrites; never build, time or run a workload."""
import argparse
import hashlib
import json
from pathlib import Path
import re

RUN_KEYS = ('ordinal', 'ruleset', 'path', 'iterations', 'epoch', 'logical_matches',
            'executed_bindings', 'changed')


def load(p):
    return json.loads(p.read_text())


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def work(value):
    if isinstance(value, dict):
        return {k: work(v) for k, v in value.items()
                if not k.endswith('_seconds') and k not in ('local_witness_contexts', 'local_witness_history_borrows')}
    return [work(v) for v in value] if isinstance(value, list) else value


def check(root, commit, phase):
    assert load(root / 'semantic-acceptance.json')['status'] == 'pass'
    history = phase == 'history'
    result = {'scope': 'standalone Cell CPU; short semantic/work checks, no new timing or allocation audit',
              'baseline_commit': '50e12acf' if history else 'ab33d47c', 'candidate_commit': commit,
              'features': 'sparse-cells,view-ports,storage-metrics',
              'semantic_acceptance': 'pass', 'cases': {}, 'tests': {},
              'timing_cadence': {'last_timed_commit': 'ab33d47c', 'implementation_commits_since_timing': 2 if history else 1},
              'performance_status': 'prior_regression_unresolved_no_new_speed_claim'}
    cases = ('full',) if history else ('reused', 'replaced', 'borrowed', 'full')
    for case, prefix in [('sum_bits', 'run')] + [(c, f'fixtures/{c}') for c in cases]:
        paths = [root / f'{prefix}-{lane}' for lane in ('baseline', 'candidate')]
        a, b = [load(p / 'report.json') for p in paths]
        program = root / ('sum/program.json' if case == 'sum_bits' else f'fixtures/{case}.json')
        assert all(r['status'] == 'complete' and r['program_sha256'] == load(program)['sha256'] for r in (a, b))
        runs = [[s[k] for k in RUN_KEYS] for s in a['steps']]
        assert runs == [[s[k] for k in RUN_KEYS] for s in b['steps']]
        for group in ('stats', 'cell_ownership', 'stable_ports'):
            assert work(a[group]) == work(b[group]), (case, group)
        assert work(a['stage_spine']['stats']) == work(b['stage_spine']['stats']), case
        contexts = [r['stage_spine']['stats']['local_witness_contexts'] for r in (a, b)]
        assert contexts == ([0, 0] if history else {'sum_bits': [12, 0], 'full': [2, 0]}.get(case, [0, 0]))
        borrows = [r['stage_spine']['stats']['local_witness_history_borrows'] for r in (a, b)]
        expected_borrows = [2, 0 if history else 2] if case == 'full' else [0, 0]
        assert borrows == expected_borrows
        files = ('state.json',) if case == 'sum_bits' else ('state.json', 'stages.json', 'binding-audit.json')
        hashes = {file: sha(paths[0] / file) for file in files}
        assert all(sha(paths[1] / file) == digest for file, digest in hashes.items())
        result['cases'][case] = {'runs': len(runs), 'ordered_hashes': hashes,
            'program_file_sha256': sha(program), 'physical_context_reads_before_after': contexts,
            'history_handle_copies_before_after': borrows,
            'remaining_runtime_port_ownership_and_spine_work_identical': True}
    a, b = [load(root / f'metrics-{lane}.json') for lane in ('baseline', 'candidate')]
    for lane, data in zip(('baseline', 'candidate'), (a, b)):
        assert data['sources']['report']['sha256'] == sha(root / f'run-{lane}/report.json')
        assert data['sources']['program']['sha256'] == sha(root / 'sum/program.json')
    metrics = {k: v for k, v in a['metrics'].items()
               if not any(s in k for s in ('_seconds', '_ns ', '/phases/', 'peak_rss'))}
    changes = {k: [v, b['metrics'][k]] for k, v in metrics.items() if b['metrics'][k] != v}
    assert list(changes) == ([] if history else ['report:/stage_spine/stats/local_witness_contexts [value]'])
    assert len(metrics) == 326
    result['work_metrics'] = {'unchanged_values_or_missing_status': len(metrics) - len(changes), 'changed': changes}
    tests = {'final-tests': 15, 'dispatch': 2} if history else {'final-tests': 18, 'iterative-tests': 18}
    for name, count in tests.items():
        path = root / f'test-{name}.log'
        passed = re.findall(r'test result: ok\. (\d+) passed; 0 failed;', path.read_text())
        assert sum(map(int, passed)) == count
        result['tests'][name] = {'passed': count, 'log_sha256': sha(path)}
    path = root / 'test-minimal.log'
    assert 'Finished `dev` profile' in path.read_text()
    result['tests']['minimal'] = {'status': 'pass', 'log_sha256': sha(path)}
    result['binaries'] = {lane: sha(root / f'runtime-{lane}') for lane in ('baseline', 'candidate')}
    fixture_runs = load(root / 'fixtures/runs.json')
    assert len(fixture_runs) == len(cases) * 2
    for row in fixture_runs:
        assert row['runtime_sha256'] == result['binaries'][row['lane']]
        assert row['diagnostic_process_seconds'] < 1
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--phase', choices=('producer', 'history'), default='producer')
    args = parser.parse_args()
    args.output.write_text(json.dumps(check(args.root, args.commit, args.phase), indent=2) + '\n')
