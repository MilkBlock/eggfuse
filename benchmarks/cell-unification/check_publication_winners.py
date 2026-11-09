#!/usr/bin/env python3
"""Verify winner-only Cell publication validation from saved work and semantics."""
import argparse
import json
from pathlib import Path
import re
from check_links import load, sha
from check_mixed_outputs import pair, ALLOWED, CHARGED

WINNERS = {'/stage_spine/stats/' + k for k in ('receipt_attempts', 'receipt_hits', 'receipt_hits_by_source/effect')}
WINNERS.add('/entry_schedule/stats/publication_pending_reuses')
COST = CHARGED | {'/stage_spine/stats/cell_output_deliveries'}


def collect(root, commit):
    program = root / 'sum/program.json'
    result = pair(root, ('run-baseline', 'run-candidate'), program, allowed=WINNERS, charged=COST)
    assert result['publication_net_saved_operations'] > 0
    before_mixed = pair(root, ('run-before-mixed', 'run-candidate'), program, allowed=ALLOWED, charged=COST)
    mixed_only = pair(root, ('run-before-mixed', 'run-baseline'), program, allowed=ALLOWED, charged=COST)
    semantic = load(root / 'semantic-acceptance.json')
    assert semantic['status'] == 'pass'
    assert semantic['input_sha256']['cpu_values'] == result['ordered_hashes']['state.json']
    metrics = []
    for lane in ('baseline', 'candidate'):
        data = load(root / f'metrics-{lane}.json')
        assert data['sources']['report']['sha256'] == sha(root / f'run-{lane}/report.json')
        assert data['sources']['program']['sha256'] == sha(program)
        metrics.append({k: v for k, v in data['metrics'].items()
            if not any(s in k for s in ('_seconds', '_ns ', '/phases/', 'peak_rss'))})
    assert metrics[0].keys() == metrics[1].keys()
    changes = {k: [v, metrics[1][k]] for k, v in metrics[0].items() if v != metrics[1][k]}
    assert all(k.startswith('report:') and k[7:].split(' [')[0] in WINNERS for k in changes)
    fixtures = {}
    for audit in (True, False):
        suffix = '' if audit else '-normal'
        records = load(root / f'fixture-runs{suffix}.json')
        assert len(records) == 8
        assert {(r['case'], r['lane'], r['bits']) for r in records} == {
            (case, lane, bits) for case in ('mixed', 'aliased') for lane in ('baseline', 'candidate') for bits in (64, 0)}
        for r in records:
            assert r['diagnostic_process_seconds'] < 1
            assert r['env'] == {'CELL_CPU_HASH_BITS': str(r['bits'])}
            runtime = root / f'runtime-{r["lane"]}'
            fixture = root / f'fixture-{r["case"]}'
            expected = [str(runtime), '--program', str(fixture / 'program.json'), '--output',
                str(fixture / f'{r["lane"]}-{r["bits"]}{suffix}'), '--local-congruence']
            assert r['argv'] == expected + (['--audit-stages'] if audit else [])
            assert r['runtime_sha256'] == sha(runtime)
            assert r['program_sha256'] == sha(fixture / 'program.json')
        for case in ('mixed', 'aliased'):
            fixture = root / f'fixture-{case}'
            for bits in (64, 0):
                f = pair(fixture, (f'baseline-{bits}{suffix}', f'candidate-{bits}{suffix}'),
                    fixture / 'program.json', audit, allowed=WINNERS, charged=COST)
                if not audit:
                    assert f['publication_net_saved_operations'] > 0
                    assert '/stage_spine/stats/receipt_attempts' in f['changed_work']
                fixtures[f'{case}-{bits}{suffix}'] = f
    tests = {}
    for name, count in (('entry', 2), ('publications', 7), ('publications-all', 7), ('scoped', 12), ('credit', 4)):
        path = root / f'test-{name}.log'
        assert sum(map(int, re.findall(r'test result: ok\. (\d+) passed; 0 failed;', path.read_text()))) == count
        tests[name] = dict(passed=count, sha256=sha(path))
    assert 'Finished `dev` profile' in (root / 'test-minimal.log').read_text()
    scoped = load(root / 'scoped-executor.json')
    assert not scoped['after_seed']['executor']['global_observer']
    assert scoped['after_b_consumption']['executor']['stats']['published_tables_while_pending'] > 0
    assert scoped['final_state_and_ordered_step_bindings_match']
    relower = load(root / 'relower.json')
    assert relower['status'] == 'pass' and relower['program_sha256'] == load(program)['sha256']
    result.update(scope='standalone Cell CPU; normal release work checks; no timing or allocator campaign',
        baseline_commit='3e8c8680', candidate_commit=commit, semantic_acceptance='pass',
        unchanged_work_metrics=len(metrics[0]) - len(changes), changed_work_metrics=changes,
        before_mixed_commit='3e622300', before_mixed=before_mixed,
        prior_mixed_step_under_current_credit=mixed_only['publication_net_saved_operations'],
        fixtures=fixtures, tests=tests, minimal_sha256=sha(root / 'test-minimal.log'),
        scoped_sha256=sha(root / 'scoped-executor.json'), relower_sha256=sha(root / 'relower.json'),
        relower_components=len(relower['components']),
        binaries={lane: sha(root / f'runtime-{lane}') for lane in ('baseline', 'candidate')},
        fixture_manifest_sha256={suffix:sha(root / f'fixture-runs{suffix}.json') for suffix in ('', '-normal')},
        removed='Independent publication-slot preparation before winner selection. Existing Cell Entry batch proof now rejects losers before visibility validation or pending maintenance. Only successful validation creates/replaces a publication; later batches revalidate.',
        limits='Entry lookups, candidate counts, output scans, receipt resolutions and real publication writes are unchanged. Every Cell output delivery still resolves its receipt; Work now charges this separately from visibility attempts, using the same corrected basis for both controls. No extra instance cache or subscription is added. Equal-weight credit is not a time model; marker/Bake unification and final parallel acceptance remain incomplete.',
        timing_cadence=dict(last_timed_commit='acab2911', implementation_commits_since_timing=3))
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--commit', required=True)
    args = p.parse_args()
    args.output.write_text(json.dumps(collect(args.root, args.commit), indent=2) + '\n')
