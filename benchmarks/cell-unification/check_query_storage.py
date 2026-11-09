#!/usr/bin/env python3
"""Check shared query storage bounds and the five-commit timing checkpoint."""
import argparse
import json
from pathlib import Path
import re

from check_links import load, sha, work
from check_context import GROUPS, RUN_KEYS, prior
from collect_sieve import timing


def check(root, commit, timed):
    assert load(root / 'semantic-acceptance.json')['status'] == 'pass'
    cases = {}
    stable = lambda value: prior(work(value), ('cell_query_result_writes',))
    for case, prefix, program in [('sum_bits', 'run', 'sum/program.json')] + [
            (case, f'fixtures/{case}', f'fixtures/{case}.json')
            for case in ('reused', 'replaced', 'borrowed', 'full')]:
        paths = [root / f'{prefix}-{lane}' for lane in ('baseline', 'candidate')]
        a, b = [load(p / 'report.json') for p in paths]
        assert all(r['status'] == 'complete' and r['program_sha256'] == load(root / program)['sha256'] for r in (a, b))
        assert [[s[k] for k in RUN_KEYS] for s in a['steps']] == [[s[k] for k in RUN_KEYS] for s in b['steps']]
        for group in GROUPS:
            assert stable(a[group]) == stable(b[group]), (case, group)
        writes = [r['stage_spine']['stats']['cell_query_result_writes'] for r in (a, b)]
        assert writes[1] <= writes[0]
        if case == 'sum_bits': assert writes[1] < writes[0]
        files = ('state.json',) if case == 'sum_bits' else ('state.json', 'stages.json', 'binding-audit.json')
        hashes = {f: sha(paths[0] / f) for f in files}
        assert all(sha(paths[1] / f) == digest for f, digest in hashes.items())
        cases[case] = {'runs': len(a['steps']), 'program_file_sha256': sha(root / program),
                      'ordered_hashes': hashes, 'stage_result_writes': writes,
                      'remaining_report_work_unchanged': GROUPS}
    metrics = []
    for lane in ('baseline', 'candidate'):
        data = load(root / f'metrics-{lane}.json')
        assert data['sources']['report']['sha256'] == sha(root / f'run-{lane}/report.json')
        assert data['sources']['program']['sha256'] == sha(root / 'sum/program.json')
        metrics.append({k: v for k, v in data['metrics'].items()
                        if not any(s in k for s in ('_seconds', '_ns ', '/phases/', 'peak_rss'))})
    changes = {k: [v, metrics[1][k]] for k, v in metrics[0].items() if v != metrics[1][k]}
    assert list(changes) == ['report:/stage_spine/stats/cell_query_result_writes [value]']
    tests = {}
    for name, count in (('query', 3), ('witness', 8), ('prefix', 6), ('entry', 1), ('context', 1), ('credit', 4)):
        path = root / f'test-{name}.log'
        passed = re.findall(r'test result: ok\. (\d+) passed; 0 failed;', path.read_text())
        assert sum(map(int, passed)) == count, name
        tests[name] = {'passed': count, 'log_sha256': sha(path)}
    path = root / 'test-minimal.log'
    assert 'Finished `dev` profile' in path.read_text()
    tests['minimal'] = {'status': 'pass', 'log_sha256': sha(path)}
    binaries = {lane: sha(root / f'runtime-{lane}') for lane in ('baseline', 'candidate')}
    fixture_runs = load(root / 'fixtures/runs.json')
    assert len(fixture_runs) == 8
    assert all(row['runtime_sha256'] == binaries[row['lane']] and row['diagnostic_process_seconds'] < 1
               for row in fixture_runs)
    result = {'scope': 'standalone Cell CPU; normal release; not native egglog performance',
        'features': 'sparse-cells,view-ports,storage-metrics', 'baseline_commit': '6b4c670d',
        'candidate_commit': commit, 'semantic_acceptance': 'pass', 'cases': cases,
        'unchanged_work_metrics': len(metrics[0]) - len(changes), 'changed_work_metrics': changes,
        'tests': tests, 'binaries': binaries,
        'storage_bound': 'One width per compiled Cell Query, shared by context, complete Entry and register execution. Register frames use the maximum width across the rule pivots; the one-time max scan and static header are not operation-instrumented.',
        'limits': 'Only trailing bound-result writes are removed from complete Entries. Interior holes keep instruction-position addresses. Scratch initialization reductions are structural, not measured allocation savings. Work weights remain uncalibrated; full rewrite, Raytrace and multithreading acceptance remain pending.'}
    result['timing_cadence'] = {'last_timed_commit': commit if timed else '7f4e24c2',
        'implementation_commits_since_timing': 0 if timed else 5,
        'implementation_commits_in_batch': ['7b8ed749', 'a02f2148', '0b3231c2', '6b4c670d', commit]}
    if timed:
        result['timing'] = timing(root, commit, commits={'baseline': '6b4c670d', 'candidate': commit,
            'last_timed': '7f4e24c2', 'historical': '24c4ae8a'})
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--commit', required=True)
    p.add_argument('--timing', action='store_true')
    args = p.parse_args()
    args.output.write_text(json.dumps(check(args.root, args.commit, args.timing), indent=2) + '\n')
