#!/usr/bin/env python3
"""Check completed Cell output takeover, including its added work; no reruns."""
import argparse
import json
from pathlib import Path
import re
from check_links import load, sha, work
from check_context import RUN_KEYS
from check_view_query import stable

SPINE = '''cell_output_checks cell_output_deliveries cell_output_receipts cell_output_slot_reads
cell_output_slots cell_output_spans completion_boundary_reads completion_boundary_records
completion_order_checks direct_publication_hash_probes effect_output_copies effect_outputs_reused
fragment_deliveries fragment_delivery_checks fragment_direct_inserts_avoided fragment_receipts
peak_cell_output_slots receipt_attempts receipt_hits receipt_hits_by_source/effect receipt_redirects'''.split()
ENTRY = 'publication_candidate_checks publication_pending_reuses publication_loser_skips publication_slot_probes'.split()
ALLOWED = {f'/{group}/stats/{k}' for group, keys in [('stage_spine', SPINE), ('entry_schedule', ENTRY)] for k in keys}
# These are the changed charged operations in Work::read. Coverage subsets are
# deliberately absent. All other work is checked unchanged, so it cancels out.
CHARGED = {f'/stage_spine/stats/{k}' for k in '''direct_publication_hash_probes
cell_output_receipts cell_output_slot_reads effect_output_copies receipt_attempts
completion_boundary_records completion_boundary_reads completion_order_checks'''.split()}
CHARGED.add('/entry_schedule/stats/publication_slot_probes')


def differences(a, b, path=''):
    if isinstance(a, dict) and isinstance(b, dict):
        assert a.keys() == b.keys(), path
        return {k: v for name in a for k, v in differences(a[name], b[name], path + '/' + name).items()}
    return {} if a == b else {path: [a, b]}


def pair(directory, lanes, program, audit=False):
    reports = [load(directory / lane / 'report.json') for lane in lanes]
    clean = [stable(work(r)) for r in reports]
    for r in clean:
        assert r['status'] == 'complete' and r['program_sha256'] == load(program)['sha256']
        r['steps'] = [[s[k] for k in RUN_KEYS] for s in r['steps']]
        for k in ('peak_rss_through_setup_bytes', 'peak_rss_through_inference_bytes'):
            r.pop(k)
    changes = differences(*clean)
    assert changes.keys() <= ALLOWED, changes.keys() - ALLOWED
    files = ('state.json', 'stages.json', 'binding-audit.json') if audit else ('state.json',)
    hashes = {f: sha(directory / lanes[0] / f) for f in files}
    assert all(sha(directory / lanes[1] / f) == h for f, h in hashes.items())
    return dict(runs=len(reports[0]['steps']), ordered_hashes=hashes, changed_work=changes,
        publication_net_saved_operations=sum(before - after for k, (before, after) in changes.items() if k in CHARGED),
        program_sha256=sha(program))


def collect(root, commit):
    result = pair(root, ('run-baseline', 'run-candidate'), root / 'sum/program.json')
    acceptance = load(root / 'semantic-acceptance.json')
    assert acceptance['status'] == 'pass'
    assert acceptance['input_sha256']['cpu_values'] == result['ordered_hashes']['state.json']
    metrics = []
    for lane in ('baseline', 'candidate'):
        data = load(root / f'metrics-{lane}.json')
        assert data['sources']['report']['sha256'] == sha(root / f'run-{lane}/report.json')
        assert data['sources']['program']['sha256'] == sha(root / 'sum/program.json')
        metrics.append({k: v for k, v in data['metrics'].items()
            if not any(s in k for s in ('_seconds', '_ns ', '/phases/', 'peak_rss'))})
    assert metrics[0].keys() == metrics[1].keys()
    changes = {k: [v, metrics[1][k]] for k, v in metrics[0].items() if v != metrics[1][k]}
    assert all(k.startswith('report:') and k[7:].split(' [')[0] in ALLOWED for k in changes)
    fixtures = {}
    manifests = {}
    for mode, directory, tail, audit, suffix in [('marked-audit', root, 'compiled/program.json', True, ''),
            ('direct-audit', root / 'raw', 'program.json', True, ''),
            ('direct-normal', root / 'raw', 'program.json', False, '-normal')]:
        manifest = directory / f'fixture-runs{suffix}.json'
        runs = load(manifest)
        assert len(runs) == 8
        assert {(r['case'], r['lane'], r['bits']) for r in runs} == {
            (case, lane, bits) for case in ('mixed', 'aliased') for lane in ('baseline', 'candidate') for bits in (64, 0)}
        for r in runs:
            assert r['diagnostic_process_seconds'] < 1
            assert r['env'] == {'CELL_CPU_HASH_BITS': str(r['bits'])}
            runtime = directory / f'runtime-{r["lane"]}'
            fixture = directory / f'fixture-{r["case"]}'
            program = fixture / tail
            assert r['runtime_sha256'] == sha(runtime) and r['program_sha256'] == sha(program)
            expected = [str(runtime), '--program', str(program), '--output',
                str(fixture / f'{r["lane"]}-{r["bits"]}{suffix}'), '--local-congruence']
            assert r['argv'] == expected + (['--audit-stages'] if audit else [])
        manifests[mode] = sha(manifest)
        for case in ('mixed', 'aliased'):
            fixture = directory / f'fixture-{case}'
            for bits in (64, 0):
                f = pair(fixture, (f'baseline-{bits}{suffix}', f'candidate-{bits}{suffix}'), fixture / tail, audit)
                if not audit:
                    stats = load(fixture / f'candidate-{bits}{suffix}/report.json')['stage_spine']['stats']
                    assert stats['fragment_receipts'] > 0 and stats['effect_outputs_reused'] > 0
                    assert stats['direct_publication_hash_probes'] == 0 and stats['completion_boundary_records'] > 0
                    assert (stats['effect_aborted_frames'] > 0) == (case == 'aliased')
                fixtures[f'{mode}-{case}-{bits}'] = f
    tests = {}
    for name, count in (('publications', 7), ('normal', 7), ('witness', 8), ('credit', 4), ('scoped', 1)):
        path = root / f'test-{name}.log'
        assert sum(map(int, re.findall(r'test result: ok\. (\d+) passed; 0 failed;', path.read_text()))) == count
        tests[name] = dict(passed=count, sha256=sha(path))
    assert 'Finished `dev` profile' in (root / 'test-minimal.log').read_text()
    scoped = load(root / 'scoped-executor.json')
    assert not scoped['after_seed']['executor']['global_observer']
    assert scoped['after_b_consumption']['executor']['stats']['published_tables_while_pending'] > 0
    assert scoped['final_state_and_ordered_step_bindings_match']
    relower = load(root / 'relower.json')
    assert relower['status'] == 'pass' and relower['program_sha256'] == load(root / 'sum/program.json')['sha256']
    result.update(scope='standalone Cell CPU; frozen normal release; work checks, not timing or allocator measurements',
        baseline_commit='3e622300', candidate_commit=commit, semantic_acceptance='pass',
        unchanged_work_metrics=len(metrics[0]) - len(changes), changed_work_metrics=changes,
        fixtures=fixtures, fixture_manifests=manifests, tests=tests,
        minimal_sha256=sha(root / 'test-minimal.log'), scoped_sha256=sha(root / 'scoped-executor.json'),
        relower_components=len(relower['components']), relower_sha256=sha(root / 'relower.json'),
        binaries={lane: sha(root / f'runtime-{lane}') for lane in ('baseline', 'candidate')},
        removed='Whole-Cell eligibility gate. The Cell effect layout retains a dense prefix of permanent Entry-owned outputs; boundary receipts follow transiently. Covered mixed outputs bypass the independent receipt hash and ready-boundary records. Source operation positions still merge publication order.',
        limits='Uncovered boundary paths remain. More uncoalesced candidates reach Entry and more output slots remain live. Equal-weight Bake credit charges those costs and is not a time model. Static width replaces a bool per rule and configuration partitions outputs once. Audit-stages disables compiled receipt delivery: direct-normal cases and normal unit tests verify takeover, audited cases verify stages. Marker prefix materialization, general Bake composition and full parallel acceptance remain unfinished.',
        timing_cadence=dict(last_timed_commit='acab2911', implementation_commits_since_timing=2))
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--commit', required=True)
    args = p.parse_args()
    args.output.write_text(json.dumps(collect(args.root, args.commit), indent=2) + '\n')
