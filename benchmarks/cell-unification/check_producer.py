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
                if not k.endswith('_seconds') and k != 'local_witness_contexts'}
    return [work(v) for v in value] if isinstance(value, list) else value


def check(root, commit):
    assert load(root / 'semantic-acceptance.json')['status'] == 'pass'
    result = {'scope': 'standalone Cell CPU; short semantic/work checks, no new timing or allocation audit',
              'baseline_commit': 'ab33d47c', 'candidate_commit': commit,
              'features': 'sparse-cells,view-ports,storage-metrics',
              'semantic_acceptance': 'pass', 'cases': {}, 'tests': {},
              'timing_cadence': {'last_timed_commit': 'ab33d47c', 'implementation_commits_since_timing': 1},
              'performance_status': 'prior_regression_unresolved_no_new_speed_claim'}
    for case, prefix in [('sum_bits', 'run')] + [(c, f'fixtures/{c}') for c in ('reused', 'replaced', 'borrowed', 'full')]:
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
        assert contexts == {'sum_bits': [12, 0], 'full': [2, 0]}.get(case, [0, 0])
        files = ('state.json',) if case == 'sum_bits' else ('state.json', 'stages.json', 'binding-audit.json')
        hashes = {file: sha(paths[0] / file) for file in files}
        assert all(sha(paths[1] / file) == digest for file, digest in hashes.items())
        result['cases'][case] = {'runs': len(runs), 'ordered_hashes': hashes,
            'program_file_sha256': sha(program), 'physical_context_reads_before_after': contexts,
            'remaining_runtime_port_ownership_and_spine_work_identical': True}
    a, b = [load(root / f'metrics-{lane}.json') for lane in ('baseline', 'candidate')]
    for lane, data in zip(('baseline', 'candidate'), (a, b)):
        assert data['sources']['report']['sha256'] == sha(root / f'run-{lane}/report.json')
        assert data['sources']['program']['sha256'] == sha(root / 'sum/program.json')
    metrics = {k: v for k, v in a['metrics'].items()
               if not any(s in k for s in ('_seconds', '_ns ', '/phases/', 'peak_rss'))}
    changes = {k: [v, b['metrics'][k]] for k, v in metrics.items() if b['metrics'][k] != v}
    assert list(changes) == ['report:/stage_spine/stats/local_witness_contexts [value]']
    assert len(metrics) == 326
    result['work_metrics'] = {'unchanged_values_or_missing_status': len(metrics) - 1, 'changed': changes}
    for name in ('final-tests', 'iterative-tests'):
        path = root / f'test-{name}.log'
        passed = re.findall(r'test result: ok\. (\d+) passed; 0 failed;', path.read_text())
        assert sum(map(int, passed)) == 18
        result['tests'][name] = {'passed': 18, 'log_sha256': sha(path)}
    path = root / 'test-minimal.log'
    assert 'Finished `dev` profile' in path.read_text()
    result['tests']['minimal'] = {'status': 'pass', 'log_sha256': sha(path)}
    result['binaries'] = {lane: sha(root / f'runtime-{lane}') for lane in ('baseline', 'candidate')}
    for row in load(root / 'fixtures/runs.json'):
        assert row['runtime_sha256'] == result['binaries'][row['lane']]
        assert row['diagnostic_process_seconds'] < 1
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--commit', required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(check(args.root, args.commit), indent=2) + '\n')
