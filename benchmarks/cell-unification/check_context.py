#!/usr/bin/env python3
"""Check static Cell prefix scopes against saved, counter-instrumented old execution."""
import argparse
import json
from pathlib import Path
import re

from check_links import load, sha, work

COUNTERS = ('prefix_copies', 'prefix_slots_copied', 'branch_slot_clears')
GROUPS = ('stats', 'cell_ownership', 'stable_ports', 'free_join', 'sieve',
          'neighbor_context', 'physical', 'stage_spine', 'local_context')
RUN_KEYS = ('ordinal', 'ruleset', 'path', 'iterations', 'epoch', 'logical_matches',
            'executed_bindings', 'changed')


def prior(value):
    if isinstance(value, dict):
        return {k: prior(v) for k, v in value.items() if k not in COUNTERS}
    return [prior(v) for v in value] if isinstance(value, list) else value


def check(root, commit):
    assert load(root / 'semantic-acceptance.json')['status'] == 'pass'
    reports = {lane: load(root / f'run-{lane}/report.json')
               for lane in ('original', 'baseline', 'candidate')}
    a = reports['baseline']
    program = root / 'sum/program.json'
    state = sha(root / 'run-baseline/state.json')
    runs = [[s[k] for k in RUN_KEYS] for s in a['steps']]
    for lane, r in reports.items():
        assert r['status'] == 'complete' and r['program_sha256'] == load(program)['sha256']
        assert sha(root / f'run-{lane}/state.json') == state
        assert [[s[k] for k in RUN_KEYS] for s in r['steps']] == runs
        for group in GROUPS:
            assert prior(work(a[group])) == prior(work(r[group])), (lane, group)
    metrics = []
    for lane in ('baseline', 'candidate'):
        data = load(root / f'metrics-{lane}.json')
        assert data['sources']['report']['sha256'] == sha(root / f'run-{lane}/report.json')
        assert data['sources']['program']['sha256'] == sha(program)
        metrics.append({k: v for k, v in data['metrics'].items()
                        if not any(s in k for s in ('_seconds', '_ns ', '/phases/', 'peak_rss'))})
    changes = {k: [v, metrics[1][k]] for k, v in metrics[0].items() if v != metrics[1][k]}
    assert len(changes) == 3 and all(any(f in k for f in COUNTERS) for k in changes)
    totals = {lane: {field: sum(row[field] for row in reports[lane]['local_context']['rules'].values())
                    for field in COUNTERS} for lane in ('baseline', 'candidate')}
    tests = {}
    for name, count in (('context', 1), ('cuts', 1), ('budget', 1), ('credit', 4)):
        p = root / f'test-{name}.log'
        passed = re.findall(r'test result: ok\. (\d+) passed; 0 failed;', p.read_text())
        assert sum(map(int, passed)) == count, name
        tests[name] = {'passed': count, 'log_sha256': sha(p)}
    p = root / 'test-minimal.log'
    assert 'Finished `dev` profile' in p.read_text()
    tests['minimal'] = {'status': 'pass', 'log_sha256': sha(p)}
    patch = Path(__file__).resolve().with_name('context-copy-baseline.patch')
    assert sha(patch) == sha(root / 'baseline.patch')
    fixture = root / 'fixture'
    fp = load(fixture / 'program.json')
    fa, fb = [load(fixture / f'{lane}/report.json') for lane in ('baseline', 'candidate')]
    assert all(r['status'] == 'complete' and r['program_sha256'] == fp['sha256'] for r in (fa, fb))
    assert [[s[k] for k in RUN_KEYS] for s in fa['steps']] == [[s[k] for k in RUN_KEYS] for s in fb['steps']]
    for group in GROUPS:
        assert prior(work(fa[group])) == prior(work(fb[group])), ('fixture', group)
    hashes = {f: sha(fixture / 'baseline' / f) for f in ('state.json', 'stages.json', 'binding-audit.json')}
    assert all(sha(fixture / 'candidate' / f) == digest for f, digest in hashes.items())
    cases = {}
    for name in ('guarded-prefix', 'linear-prefix'):
        rid = next(i for i, r in enumerate(fp['recipe']['rules']) if r['metadata']['name'] == name)
        before, after = [r['local_context']['rules'][str(rid)] for r in (fa, fb)]
        assert before['calls'] > 0 and after['delta_terminal_rows'] > 0
        for orientation in after['orientations']:
            cut = next(c for c in fp['context_cuts'][rid] if c[0] == int(orientation))
            calls = [fp['recipe']['rules'][rid]['query'][i]['call'] for i in cut[1]]
            assert any('primitive' in c for c in calls)
            assert any('table' in c for c in calls) == (name == 'guarded-prefix')
        if name == 'linear-prefix':
            assert all(before[f] == after[f] == 0 for f in COUNTERS)
        else:
            assert after['prefix_copies'] < before['prefix_copies']
            assert after['branch_slot_clears'] > 0
        cases[name] = {f: [before[f], after[f]] for f in COUNTERS}
    return {
        'scope': 'standalone Cell CPU; normal release; no timing or allocation audit',
        'baseline_source_commit': '7b8ed749', 'candidate_commit': commit,
        'baseline_instrumentation': {'patch': str(patch.relative_to(Path(__file__).resolve().parents[2])),
            'sha256': sha(patch), 'purpose': 'Counters only, same old prefix-copy algorithm. Missing counters in the original report are not treated as zero.'},
        'semantic_acceptance': 'pass', 'runs': len(runs), 'state_sha256': state,
        'program_file_sha256': sha(program), 'unchanged_report_groups_excluding_new_counters': GROUPS,
        'unchanged_work_metrics': len(metrics[0]) - len(changes), 'changed_work_metrics': changes,
        'prefix_work': totals,
        'prefix_work_net_equal_weight_units_saved': sum(totals['baseline'].values()) - sum(totals['candidate'].values()),
        'tests': tests,
        'guarded_fixture': {'runs': len(fb['steps']), 'program_file_sha256': sha(fixture / 'program.json'),
            'source_sha256': sha(Path(__file__).resolve().with_name('context-branches.egg')),
            'ordered_hashes': hashes, 'cases': cases,
            'admission': 'explicitly enabled compiler-certified contexts; no performance training claimed'},
        'binaries': {lane: sha(root / f'runtime-{lane}') for lane in reports},
        'reports': {lane: sha(root / f'run-{lane}/report.json') for lane in reports},
        'timing_cadence': {'last_timed_commit': '7f4e24c2', 'implementation_commits_since_timing': 2},
        'limits': 'Copies count source clone operations and allocated array slots, including empty slots, not allocator calls or bytes. Clears include unassigned fields after early failures. Equal weights are not a time model or an exhaustive instruction count. Cached successful prefixes, leases and terminal post-guard copies remain; no full context takeover, speedup or multithread acceptance claimed.'}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--commit', required=True)
    args = p.parse_args()
    args.output.write_text(json.dumps(check(args.root, args.commit), indent=2) + '\n')
