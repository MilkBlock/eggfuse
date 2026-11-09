#!/usr/bin/env python3
"""Check static Cell prefix scopes against saved, counter-instrumented old execution."""
import argparse
import json
from pathlib import Path
import re

from check_links import load, sha, work

COUNTERS = ('prefix_copies', 'prefix_slots_copied', 'branch_slot_clears')
TERMINAL = ('terminal_binding_copies', 'terminal_slots_copied',
            'terminal_scratch_slots', 'terminal_result_writes')
GROUPS = ('stats', 'cell_ownership', 'stable_ports', 'free_join', 'sieve',
          'neighbor_context', 'physical', 'stage_spine', 'local_context')
RUN_KEYS = ('ordinal', 'ruleset', 'path', 'iterations', 'epoch', 'logical_matches',
            'executed_bindings', 'changed')


def prior(value, counters=COUNTERS):
    if isinstance(value, dict):
        return {k: prior(v, counters) for k, v in value.items() if k not in counters}
    return [prior(v, counters) for v in value] if isinstance(value, list) else value


def check_prefix(root, commit, phase="prefix"):
    assert load(root / 'semantic-acceptance.json')['status'] == 'pass'
    def pair(path, program, lanes):
        reports = [load(path / lane / 'report.json') for lane in lanes]
        assert all(r['status'] == 'complete' and r['program_sha256'] == load(program)['sha256'] for r in reports)
        a, b = reports
        assert [[s[k] for k in RUN_KEYS] for s in a['steps']] == [[s[k] for k in RUN_KEYS] for s in b['steps']]
        for group in GROUPS:
            assert work(a[group]) == work(b[group]), (path, group)
        files = ('state.json',) if path == root else ('state.json', 'stages.json', 'binding-audit.json')
        hashes = {f: sha(path / lanes[0] / f) for f in files}
        assert all(sha(path / lanes[1] / f) == digest for f, digest in hashes.items())
        return {'runs': len(a['steps']), 'ordered_hashes': hashes,
                'program_file_sha256': sha(program), 'context_work': b['local_context']['rules']}
    result = pair(root, root / 'sum/program.json', ('run-baseline', 'run-candidate'))
    metrics = []
    for lane in ('baseline', 'candidate'):
        data = load(root / f'metrics-{lane}.json')
        assert data['sources']['report']['sha256'] == sha(root / f'run-{lane}/report.json')
        assert data['sources']['program']['sha256'] == sha(root / 'sum/program.json')
        metrics.append({k: v for k, v in data['metrics'].items()
                        if not any(s in k for s in ('_seconds', '_ns ', '/phases/', 'peak_rss'))})
    assert metrics[0] == metrics[1]
    fixtures = {}
    for name in ('branches', 'terminal'):
        path = root / f'fixture-{name}'
        fixtures[name] = pair(path, path / 'program.json', ('baseline', 'candidate'))
        assert any(row['calls'] > 0 for row in fixtures[name]['context_work'].values())
        fixtures[name]['source_sha256'] = sha(Path(__file__).resolve().with_name(f'context-{name}.egg'))
    tests = {}
    for name, count in (('query', 3), ('context', 1), ('cuts', 1), ('budget', 1), ('entry', 1)):
        path = root / f'test-{name}.log'
        passed = re.findall(r'test result: ok\. (\d+) passed; 0 failed;', path.read_text())
        assert sum(map(int, passed)) == count, name
        tests[name] = {'passed': count, 'log_sha256': sha(path)}
    path = root / 'test-minimal.log'
    assert 'Finished `dev` profile' in path.read_text()
    tests['minimal'] = {'status': 'pass', 'log_sha256': sha(path)}
    result = dict(result, scope='standalone Cell CPU; normal release; no timing or allocation audit',
        baseline_commit='c8ef6edc' if phase == 'selection' else '0b3231c2', candidate_commit=commit, semantic_acceptance='pass',
        unchanged_report_groups=GROUPS, unchanged_work_metrics=len(metrics[0]),
        fixtures=fixtures, tests=tests,
        binaries={lane: sha(root / f'runtime-{lane}') for lane in ('baseline', 'candidate')},
        timing_cadence={'last_timed_commit': 'c8ef6edc' if phase == 'selection' else '7f4e24c2',
                       'implementation_commits_since_timing': 1 if phase == 'selection' else 4},
        limits='Cell instruction lowering, field reads and scalar binding now cover retained prefixes. Cached prefix storage, admission, indexes, root binding and Run invalidation remain necessary. Existing counters do not count the removed Arg decoding or scalar Vec allocation; no numeric savings or speedup inferred.')
    if phase == 'selection':
        program = load(root / 'sum/program.json')
        all_cuts = program['context_cuts']
        allowed = set(program['context_admission']['rules'])
        admitted = [cuts for rid, cuts in enumerate(all_cuts) if rid in allowed]
        before, after = [sum(map(len, cuts)) for cuts in (all_cuts, admitted)]
        report = load(root / 'run-candidate/report.json')
        assert after == report['local_context']['cut_orientations'] < before
        audit = load(root / 'relower.json')
        assert audit['status'] == 'pass' and audit['program_sha256'] == program['sha256']
        assert {'context_cuts', 'local_contexts', 'multi_stage', 'row_kernels'} <= {v['component'] for v in audit['components']}
        result['relower'] = {'components': len(audit['components']), 'sha256': sha(root / 'relower.json')}
        result['general_context_preparation'] = {
            'instruction_plans_before_after': [before, after],
            'instruction_steps_before_after': [sum(len(c[1]) + 1 + len(c[3]) for row in cuts for c in row) for cuts in (all_cuts, admitted)],
            'basis': 'Exact source-path count inferred from validated candidates/admission: old code projects each selected shape before pruning; new code projects only admitted shapes. Not allocator or timed measurements.',
            'all_selection_certificates_still_validated': before,
            'default_narrow_context_path': 'unchanged; excluded from these counts'}
        result['limits'] = ('Admission is a performance choice, not a correctness proof. Full candidate shape validation, selected Cell lowering, index/cache lifetime, root binding and ordinary fallback remain. Re-fitting can widen selection from source without constructing discarded instructions. No new speed or allocation claim; complete Cell unification remains unfinished.')
    return result



def check(root, commit, phase='branches'):
    if phase in ('prefix', 'selection'):
        return check_prefix(root, commit, phase)
    terminal = phase == 'terminal'
    counters = TERMINAL if terminal else COUNTERS
    stable = lambda value: prior(work(value), counters)
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
            assert stable(a[group]) == stable(r[group]), (lane, group)
    metrics = []
    for lane in ('baseline', 'candidate'):
        data = load(root / f'metrics-{lane}.json')
        assert data['sources']['report']['sha256'] == sha(root / f'run-{lane}/report.json')
        assert data['sources']['program']['sha256'] == sha(program)
        metrics.append({k: v for k, v in data['metrics'].items()
                        if not any(s in k for s in ('_seconds', '_ns ', '/phases/', 'peak_rss'))})
    changes = {k: [v, metrics[1][k]] for k, v in metrics[0].items() if v != metrics[1][k]}
    assert len(changes) == (0 if terminal else 3)
    assert all(any(f in k for f in counters) for k in changes)
    totals = {lane: {field: sum(row[field] for row in reports[lane]['local_context']['rules'].values())
                    for field in counters} for lane in ('baseline', 'candidate')}
    tests = {}
    checks = (('query', 3), ('context', 1), ('cuts', 1), ('entry', 1), ('credit', 4)) if terminal else (
        ('context', 1), ('cuts', 1), ('budget', 1), ('credit', 4))
    for name, count in checks:
        p = root / f'test-{name}.log'
        passed = re.findall(r'test result: ok\. (\d+) passed; 0 failed;', p.read_text())
        assert sum(map(int, passed)) == count, name
        tests[name] = {'passed': count, 'log_sha256': sha(p)}
    p = root / 'test-minimal.log'
    assert 'Finished `dev` profile' in p.read_text()
    tests['minimal'] = {'status': 'pass', 'log_sha256': sha(p)}
    patch = Path(__file__).resolve().with_name(
        'context-terminal-baseline.patch' if terminal else 'context-copy-baseline.patch')
    assert sha(patch) == sha(root / 'baseline.patch')
    fixture = root / 'fixture'
    fp = load(fixture / 'program.json')
    fa, fb = [load(fixture / f'{lane}/report.json') for lane in ('baseline', 'candidate')]
    assert all(r['status'] == 'complete' and r['program_sha256'] == fp['sha256'] for r in (fa, fb))
    assert [[s[k] for k in RUN_KEYS] for s in fa['steps']] == [[s[k] for k in RUN_KEYS] for s in fb['steps']]
    for group in GROUPS:
        assert stable(fa[group]) == stable(fb[group]), ('fixture', group)
    hashes = {f: sha(fixture / 'baseline' / f) for f in ('state.json', 'stages.json', 'binding-audit.json')}
    assert all(sha(fixture / 'candidate' / f) == digest for f, digest in hashes.items())
    cases = {}
    for name in (('guarded-suffix', 'bound-suffix') if terminal else ('guarded-prefix', 'linear-prefix')):
        rid = next(i for i, r in enumerate(fp['recipe']['rules']) if r['metadata']['name'] == name)
        before, after = [r['local_context']['rules'][str(rid)] for r in (fa, fb)]
        assert before['calls'] > 0
        if name != 'bound-suffix':
            assert after['delta_terminal_rows'] > 0
        for orientation in after['orientations']:
            cut = next(c for c in fp['context_cuts'][rid] if c[0] == int(orientation))
            calls = [fp['recipe']['rules'][rid]['query'][i]['call'] for i in (cut[3] if terminal else cut[1])]
            assert any('primitive' in c for c in calls)
            assert any('table' in c for c in calls) == (name == 'guarded-prefix')
        if terminal:
            assert before['terminal_binding_copies'] > 0 and before['terminal_slots_copied'] > 0
            assert after['terminal_binding_copies'] == after['terminal_slots_copied'] == 0
            if name == 'bound-suffix':
                assert after['terminal_scratch_slots'] == after['terminal_result_writes'] == 0
            else:
                assert after['terminal_scratch_slots'] > 0 and after['terminal_result_writes'] > 0
                assert after['terminal_pairs'] > after['full_terminal_rows'] + after['delta_terminal_rows']
        elif name == 'linear-prefix':
            assert all(before[f] == after[f] == 0 for f in COUNTERS)
        else:
            assert after['prefix_copies'] < before['prefix_copies']
            assert after['branch_slot_clears'] > 0
        cases[name] = {f: [before[f], after[f]] for f in counters}
    return {
        'scope': 'standalone Cell CPU; normal release; no timing or allocation audit',
        'baseline_source_commit': 'a02f2148' if terminal else '7b8ed749', 'candidate_commit': commit,
        'baseline_instrumentation': {'patch': str(patch.relative_to(Path(__file__).resolve().parents[2])),
            'sha256': sha(patch), 'purpose': 'Counters only, same old algorithm. Missing counters in the original report are not treated as zero.'},
        'semantic_acceptance': 'pass', 'runs': len(runs), 'state_sha256': state,
        'program_file_sha256': sha(program), 'unchanged_report_groups_excluding_new_counters': GROUPS,
        'unchanged_work_metrics': len(metrics[0]) - len(changes), 'changed_work_metrics': changes,
        'terminal_work' if terminal else 'prefix_work': totals,
        'terminal_work_net_equal_weight_units_saved' if terminal else 'prefix_work_net_equal_weight_units_saved':
            sum(totals['baseline'].values()) - sum(totals['candidate'].values()),
        'tests': tests,
        'guarded_fixture': {'runs': len(fb['steps']), 'program_file_sha256': sha(fixture / 'program.json'),
            'source_sha256': sha(Path(__file__).resolve().with_name('context-terminal.egg' if terminal else 'context-branches.egg')),
            'ordered_hashes': hashes, 'cases': cases,
            'admission': 'explicitly enabled compiler-certified contexts; no performance training claimed'},
        'binaries': {lane: sha(root / f'runtime-{lane}') for lane in reports},
        'reports': {lane: sha(root / f'run-{lane}/report.json') for lane in reports},
        'timing_cadence': {'last_timed_commit': '7f4e24c2', 'implementation_commits_since_timing': 3 if terminal else 2},
        'limits': ('Sum-bits does not exercise post-guards; suffix takeover is verified by the short differential fixture. ' if terminal else '') +
            'Copies count source clone operations and array slots, including empty slots, not allocator calls or bytes. Scratch initialization and result writes are separately charged. Equal weights are not a time model or an exhaustive instruction count. Cached prefixes, leases, prefix scalar interpretation and index lifetime remain; no full context takeover, speedup or multithread acceptance claimed.'}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--commit', required=True)
    p.add_argument('--phase', choices=('branches', 'terminal', 'prefix', 'selection'), default='branches')
    args = p.parse_args()
    args.output.write_text(json.dumps(check(args.root, args.commit, args.phase), indent=2) + '\n')
