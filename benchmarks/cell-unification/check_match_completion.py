#!/usr/bin/env python3
"""Validate direct Cell match facts and the requested short timing checkpoint."""
import argparse
import json
from pathlib import Path
import re

from check_context import GROUPS, RUN_KEYS
from check_links import load, sha, work
from collect_sieve import timing


def check(root, commit, timed):
    assert load(root / 'semantic-acceptance.json')['status'] == 'pass'
    cases = {}
    for name in ('sum', 'branches', 'terminal', 'roots'):
        folder = root if name == 'sum' else root / f'fixture-{name}'
        program = root / 'sum/program.json' if name == 'sum' else folder / 'program.json'
        paths = [folder / (f'run-{lane}' if name == 'sum' else lane)
                 for lane in ('baseline', 'candidate')]
        a, b = [load(path / 'report.json') for path in paths]
        assert all(r['status'] == 'complete' and r['program_sha256'] == load(program)['sha256']
                   for r in (a, b))
        assert [[s[k] for k in RUN_KEYS] for s in a['steps']] == [[s[k] for k in RUN_KEYS] for s in b['steps']]
        for group in GROUPS:
            assert work(a[group]) == work(b[group]), (name, group)
        files = ('state.json',) if name == 'sum' else ('state.json', 'stages.json', 'binding-audit.json')
        hashes = {f: sha(paths[0] / f) for f in files}
        assert all(sha(paths[1] / f) == digest for f, digest in hashes.items())
        assert any(r['bindings'] > 0 for r in b['local_context']['rules'].values())
        cases[name] = {'runs': len(a['steps']), 'ordered_hashes': hashes,
                       'program_file_sha256': sha(program), 'compared_report_groups': GROUPS,
                       'context_bindings': sum(r['bindings'] for r in b['local_context']['rules'].values())}
    metrics = []
    for lane in ('baseline', 'candidate'):
        data = load(root / f'metrics-{lane}.json')
        assert data['sources']['report']['sha256'] == sha(root / f'run-{lane}/report.json')
        assert data['sources']['program']['sha256'] == sha(root / 'sum/program.json')
        metrics.append({k: v for k, v in data['metrics'].items()
                        if not any(s in k for s in ('_seconds', '_ns ', '/phases/', 'peak_rss'))})
    assert metrics[0] == metrics[1]
    tests = {}
    for name, count in (('facts', 2), ('context', 1), ('entry', 1), ('witness', 8), ('prefix', 6), ('receipts', 7)):
        path = root / f'test-{name}.log'
        passed = re.findall(r'test result: ok\. (\d+) passed; 0 failed;', path.read_text())
        assert sum(map(int, passed)) == count, name
        tests[name] = {'passed': count, 'log_sha256': sha(path)}
    path = root / 'test-minimal.log'
    assert 'Finished `dev` profile' in path.read_text()
    tests['minimal'] = {'status': 'pass', 'log_sha256': sha(path)}
    relower = load(root / 'relower.json')
    assert relower['status'] == 'pass' and relower['program_sha256'] == load(root / 'sum/program.json')['sha256']
    result = {
        'scope': 'standalone Cell CPU; normal release; not native egglog performance',
        'features': 'sparse-cells,view-ports,storage-metrics',
        'baseline_commit': '3d814c3a', 'candidate_commit': commit,
        'semantic_acceptance': 'pass', 'cases': cases,
        'unchanged_work_metrics': len(metrics[0]), 'changed_work_metrics': {}, 'tests': tests,
        'relower': {'components': len(relower['components']), 'sha256': sha(root / 'relower.json')},
        'binaries': {lane: sha(root / f'runtime-{lane}') for lane in ('baseline', 'candidate')},
        'takeover': 'Context emits the existing requested QueryFacts directly in Cell Matched; the full outgoing witness array and executor conversion loop are removed. Register and stage adapters use the same fact projection; full Entry still retains its intermediate witness array.',
        'limits': 'Context now projects requested facts before duplicate answers are removed, where it previously copied a full witness array. No projection/allocation counts are inferred from deduplicated binding counts. Cached-prefix witnesses and liveness checks remain. Unchanged existing counters do not establish saved work or speed; full Cell rewrite and multithreading remain incomplete.',
        'timing_cadence': {'last_timed_commit': commit if timed else 'c8ef6edc',
            'implementation_commits_since_timing': 0 if timed else 4,
            'implementation_commits_in_batch': ['30394de0', '7d773cdc', '3d814c3a', commit],
            'authorization': 'User explicitly requested a timing check after the current commit; this batch has four implementation commits. Resume every five thereafter.'}}
    if timed:
        result['timing'] = timing(root, commit, commits={'baseline': '3d814c3a', 'candidate': commit,
            'last_timed': 'c8ef6edc', 'historical': '24c4ae8a'})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--timing', action='store_true')
    args = parser.parse_args()
    args.output.write_text(json.dumps(check(args.root, args.commit, args.timing), indent=2) + '\n')
