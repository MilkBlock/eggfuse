#!/usr/bin/env python3
"""Verify Cell output selection from saved executions, without a timing run."""
import argparse
import json
from pathlib import Path
import re
from check_links import load, sha
from check_mixed_outputs import pair, ALLOWED, CHARGED

SPINE = '''alias_effect_forwards alias_query_forwards captured_anchors cell_output_checks
cell_output_deliveries cell_output_receipts cell_output_slot_reads cell_output_slots
effect_output_copies effect_outputs_reused effect_slots_initialized fragment_deliveries
fragment_delivery_checks fragment_direct_inserts_avoided fragment_receipts
peak_cell_output_slots unmaterialized_anchor_keys'''.split()
SELECTION = {'/stage_spine/stats/' + k for k in SPINE} | {
    '/entry_schedule/stats/' + k for k in (
        'publication_candidate_checks', 'publication_loser_skips', 'publication_slot_probes')}
# Audited capture still materializes keys. Removing a duplicate capture also
# removes its field reads; these are not additional runtime publication credit.
AUDIT = {'/stable_ports/stats/' + k for k in (
    'node_lookups', 'port_reads', 'root_parent_probes', 'root_resolutions')}
AUDIT.add('/storage/sealed_slot_reads')
COST = CHARGED | {'/stage_spine/stats/' + k for k in ('cell_output_deliveries', 'captured_anchors')}


def collect(root, commit):
    program = root / 'sum/program.json'
    result = pair(root, ('run-baseline', 'run-candidate'), program, allowed=SELECTION, charged=COST)
    assert result['publication_net_saved_operations'] > 0
    cumulative = pair(root, ('run-before-mixed', 'run-candidate'), program,
        allowed=ALLOWED | SELECTION, charged=COST)
    acceptance = load(root / 'semantic-acceptance.json')
    assert acceptance['status'] == 'pass'
    assert acceptance['input_sha256']['cpu_values'] == result['ordered_hashes']['state.json']
    metrics = []
    for lane in ('baseline', 'candidate'):
        data = load(root / f'metrics-{lane}.json')
        assert data['sources']['report']['sha256'] == sha(root / f'run-{lane}/report.json')
        assert data['sources']['program']['sha256'] == sha(program)
        metrics.append({k: v for k, v in data['metrics'].items()
            if not any(s in k for s in ('_seconds', '_ns ', '/phases/', 'peak_rss'))})
    assert metrics[0].keys() == metrics[1].keys()
    changes = {k: [v, metrics[1][k]] for k, v in metrics[0].items() if v != metrics[1][k]}
    assert all(k.startswith('report:') and k[7:].split(' [')[0] in SELECTION for k in changes)
    fixtures = {}
    for audit in (True, False):
        suffix = '' if audit else '-normal'
        records = load(root / f'fixture-runs{suffix}.json')
        expected = {(case, lane, bits) for case in ('mixed', 'aliased')
            for lane in ('baseline', 'candidate') for bits in (64, 0)}
        assert len(records) == len(expected)
        assert {(r['case'], r['lane'], r['bits']) for r in records} == expected
        for r in records:
            fixture = root / f'fixture-{r["case"]}'
            runtime = root / f'runtime-{r["lane"]}'
            assert r['diagnostic_process_seconds'] < 1
            assert r['env'] == {'CELL_CPU_HASH_BITS': str(r['bits'])}
            assert r['runtime_sha256'] == sha(runtime)
            assert r['program_sha256'] == sha(fixture / 'program.json')
            assert r['argv'] == [str(runtime), '--program', str(fixture / 'program.json'), '--output',
                str(fixture / f'{r["lane"]}-{r["bits"]}{suffix}'), '--local-congruence'] + (
                    ['--audit-stages'] if audit else [])
        for case in ('mixed', 'aliased'):
            fixture = root / f'fixture-{case}'
            for bits in (64, 0):
                f = pair(fixture, (f'baseline-{bits}{suffix}', f'candidate-{bits}{suffix}'),
                    fixture / 'program.json', audit, allowed=SELECTION | (AUDIT if audit else set()), charged=COST)
                if case == 'mixed':
                    assert not f['changed_work']  # Eq alone is never an alias proof.
                else:
                    assert f['publication_net_saved_operations'] > 0
                    stats = load(fixture / f'candidate-{bits}{suffix}/report.json')['stage_spine']['stats']
                    assert stats['effect_aborted_frames'] > 0
                    assert stats['alias_effect_forwards'] > 0 and stats['alias_query_forwards'] > 0
                fixtures[f'{case}-{bits}{suffix}'] = f
    tests = {}
    for name, count in (('layout', 3), ('publications', 8), ('publications-all', 8), ('witness', 8), ('scoped', 12)):
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
    result.update(scope='standalone Cell CPU; saved normal release work checks, no timing or allocator campaign',
        baseline_commit='c07c314e', candidate_commit=commit, semantic_acceptance='pass',
        unchanged_work_metrics=len(metrics[0]) - len(changes), changed_work_metrics=changes,
        before_mixed_commit='3e622300', before_mixed=cumulative, fixtures=fixtures, tests=tests,
        minimal_sha256=sha(root / 'test-minimal.log'), scoped_sha256=sha(root / 'scoped-executor.json'),
        relower_sha256=sha(root / 'relower.json'), relower_components=len(relower['components']),
        binaries={lane: sha(root / f'runtime-{lane}') for lane in ('baseline', 'candidate')},
        fixture_manifest_sha256={suffix: sha(root / f'fixture-runs{suffix}.json') for suffix in ('', '-normal')},
        removed='Earlier permanent Entry outputs sharing the same proven query/effect receipt source. Last original operation remains the continuation address; donor receipt and demanded history slots remain live.',
        limits='Selection runs while building the static Cell output layout, adding a temporary source set only for multi-output Cells with eligible aliases. Eq-only, mutable, deletable and uncovered boundaries remain; no instance index is added. Equal-weight work is not speed. Source marker materialization, general Bake composition and final parallel acceptance remain incomplete.',
        timing_cadence=dict(last_timed_commit='acab2911', implementation_commits_since_timing=4))
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--commit', required=True)
    args = p.parse_args()
    args.output.write_text(json.dumps(collect(args.root.resolve(), args.commit), indent=2) + '\n')
