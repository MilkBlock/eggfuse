#!/usr/bin/env python3
"""Check saved Cell prefix completion, metered control and short semantic runs."""
import argparse
import json
from pathlib import Path
import re
import subprocess
from check_links import load, sha
from check_mixed_outputs import pair

ALLOWED = {'/stats/' + k for k in ('handoff_attempts', 'handoff_closed', 'handoff_closed_fallback')}
ALLOWED |= {'/stage_spine/stats/' + k for k in ('effect_aborted_frames', 'effect_frames',
    'effect_slot_probes', 'effect_slot_targets', 'effect_slots_initialized')}
ALLOWED |= {'/stable_ports/stats/' + k for k in ('node_lookups', 'port_reads',
    'root_parent_probes', 'root_resolutions', 'row_views')}
ALLOWED |= {'/cell_ownership/stats/marker_union_requests', '/storage/sealed_slot_reads'}
COST = {'/stats/handoff_attempts'}  # Other charged Work fields are checked unchanged.


def compare(root, lanes, program, audit=False, allowed=ALLOWED):
    result = pair(root, lanes, program, audit, allowed=allowed, charged=COST)
    result['net_saved_measured_operations'] = result.pop('publication_net_saved_operations')
    return result


def opportunity(program, report):
    units = [[e['consumer']] for e in program['spine_blocks']['entries']]
    units += [[r] for r in program['iterative_bake'].get('producer_roots', [])]
    for j in program['iterative_bake']['joins']:
        units.append(units[j['left']] + units[j['right']])
    aliases = {(a['rule'], a['operation']) for a in program['known_results']['static_aliases']}
    switch = program['iterative_bake']['rhs_handoffs']
    unions = switch['schema'] != 'eggfuse-result-switch/v1'
    eligible, remaining = [], []
    for pc, node in enumerate(switch['states']):
        proof = node['program']
        if proof['complete'] or not proof['reuse']:
            continue
        rid = units[node['unit']][-1]
        rule = program['recipe']['rules'][rid]
        supplied = {r['op'] for r in proof['reuse']}
        needed = [op for op, e in enumerate(rule['effects']) if op not in supplied
            and e['op'] != 'copy' and not (unions and e['op'] == 'union')]
        item = dict(state=pc, unit=node['unit'], rule=rid, source_set=rule['metadata']['source_set'],
            uncovered_operations=needed, alias_operations=[op for op in needed if (rid, op) in aliases],
            prior_applied_unit_visits=report['stage_spine']['iterative_bake']['applied_units'].get(str(node['unit']), 0))
        (eligible if all((rid, op) in aliases for op in needed) else remaining).append(item)
    return dict(newly_closed=eligible, remaining=remaining,
        scope='Static retained switch certificates and prior applied-unit counts; not a mutation count or guaranteed successful closure')


def collect(root, commit):
    program = root / 'sum/program.json'
    result = compare(root, ('run-baseline', 'run-candidate'), program)
    assert result['net_saved_measured_operations'] > 0
    metering = compare(root, ('run-unmetered', 'run-baseline'), program, allowed=COST)
    assert set(metering['changed_work']) == COST
    control = root / 'control'
    git = lambda *args: subprocess.check_output(['git', '-C', str(control), *args], text=True)
    assert git('rev-parse', '--short=8', 'HEAD').strip() == '311a3ef8'
    patch = Path(__file__).with_name('closed-attempt-accounting.patch')
    assert git('diff', '--', 'engine/cell-runtime/src/graph.rs') == patch.read_text()
    assert git('diff', '--name-only').splitlines() == ['engine/cell-runtime/src/graph.rs']
    assert not git('diff', '--cached', '--name-only').strip()
    prior = load(Path(__file__).with_name('output-donors-results.json'))
    assert sha(root / 'runtime-unmetered') == prior['binaries']['candidate']
    opp = opportunity(load(program), load(root / 'run-unmetered/report.json'))
    assert opp == load(root / 'opportunity.json')
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
    assert all(k.startswith('report:') and k[7:].split(' [')[0] in ALLOWED for k in changes)
    fixtures = {}
    for audit in (True, False):
        suffix = '' if audit else '-normal'
        records = load(root / f'fixture-runs{suffix}.json')
        expected = {(case, lane, bits) for case in ('closed', 'retired', 'barrier')
            for lane in ('baseline', 'candidate') for bits in (64, 0)}
        assert len(records) == len(expected)
        assert {(r['case'], r['lane'], r['bits']) for r in records} == expected
        for r in records:
            fixture = root / f'fixture-{r["case"]}'
            runtime = root / f'runtime-{r["lane"]}'
            assert r['diagnostic_process_seconds'] < 1 and r['env'] == {'CELL_CPU_HASH_BITS': str(r['bits'])}
            assert r['runtime_sha256'] == sha(runtime) and r['program_sha256'] == sha(fixture / 'program.json')
            assert r['argv'] == [str(runtime), '--program', str(fixture / 'program.json'), '--output',
                str(fixture / f'{r["lane"]}-{r["bits"]}{suffix}'), '--local-congruence'] + (['--audit-stages'] if audit else [])
        for case, closed, resumed in [('closed', 2, 0), ('retired', 1, 1), ('barrier', 0, 0)]:
            fixture = root / f'fixture-{case}'
            for bits in (64, 0):
                f = compare(fixture, (f'baseline-{bits}{suffix}', f'candidate-{bits}{suffix}'), fixture / 'program.json', audit)
                if case == 'barrier': assert not f['changed_work']
                report = load(fixture / f'candidate-{bits}{suffix}/report.json')
                assert report['stats']['handoff_closed'] == closed
                assert report['stats']['handoff_closed_fallback'] == resumed
                assert report['stats']['handoff_attempts'] == 4
                assert report['stage_spine']['stats']['effect_aborted_frames'] == 0
                fixtures[f'{case}-{bits}{suffix}'] = f
    tests = {}
    for name, count in [('aliases', 3), ('aliases-all', 3), ('publications', 9), ('witness', 8),
            ('congruence', 1), ('barrier', 1), ('history', 1), ('scoped', 12), ('credit', 4)]:
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
    result.update(scope='standalone Cell CPU; normal release work checks, no timing or allocator campaign',
        baseline_commit='311a3ef8 plus the recorded attempt-accounting-only patch', candidate_commit=commit,
        semantic_acceptance='pass', metering_control=metering, control_patch_sha256=sha(patch), opportunity=opp,
        unchanged_work_metrics=len(metrics[0]) - len(changes), changed_work_metrics=changes, fixtures=fixtures,
        tests=tests, minimal_sha256=sha(root / 'test-minimal.log'), scoped_sha256=sha(root / 'scoped-executor.json'),
        relower_sha256=sha(root / 'relower.json'), relower_components=len(relower['components']),
        binaries={lane: sha(root / f'runtime-{lane}') for lane in ('unmetered', 'baseline', 'candidate')},
        fixture_manifest_sha256={suffix: sha(root / f'fixture-runs{suffix}.json') for suffix in ('', '-normal')},
        removed='Whole-prefix discard, receipt-frame recreation and repeated witness checks after a closed Cell miss. Iterative and structural completion share the Cell Start result; source aliases extend closure after exact portable-proof validation.',
        limits='No full-closure increase on sum-bits: newly eligible visits still miss, but now resume without duplicate work. Raw operation receipts, original effect/Run order, exact key/liveness checks and unsupported-union boundaries remain. Setup lowering and partial-frame moves are not separately timed or allocator-counted. Equal-weight credit charges actual witness attempts once; older raw counts omitted failed preflight work. Overall Cell unification and final parallel acceptance remain incomplete.',
        timing_cadence=dict(last_timed_commit='311a3ef8', implementation_commits_since_timing=1))
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--commit', required=True)
    args = p.parse_args()
    args.output.write_text(json.dumps(collect(args.root.resolve(), args.commit), indent=2) + '\n')
