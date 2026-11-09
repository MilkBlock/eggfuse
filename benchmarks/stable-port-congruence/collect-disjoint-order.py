#!/usr/bin/env python3
"""Check same-operator independence, retained fences, and complete proof costs."""
import argparse
import copy
import json
from pathlib import Path
import re
import runpy

deterministic = runpy.run_path(str(Path(__file__).with_name('collect-overlap-epochs.py')))['deterministic']


def read(path):
    return json.loads(path.read_text())


def collect(root, output):
    validation = {}
    required = ('disjoint_regions_of_the_same_operators_can_cross_source_epochs',
                'disjoint_first_outputs_cannot_hide_a_shared_downstream_condition',
                'separate_source_epochs_preserve_ordered_merge_observations',
                'frontier_independence_cannot_hide_its_membership_probes',
                'an_effective_union_commits_while_a_snapshot_reader_is_held',
                'a_reader_panic_joins_workers_and_restores_committed_overlays',
                'a_first_reader_panic_abandons_its_slots_and_releases_the_coordinator')
    for suffix, expected in (('workspace-tests', 328), ('tests', 121), ('non-sparse-tests', 121)):
        log = (root / f'disjoint-order-{suffix}.log').read_text()
        assert 'test result: FAILED' not in log
        for test in required:
            assert f'{test} ... ok' in log, (suffix, test)
        if suffix == 'workspace-tests':
            assert 'unavailable_frontiers_and_source_aliases_cannot_certify_independence ... ok' in log
        rows = [tuple(map(int, row)) for row in re.findall(
            r'test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored', log)]
        assert rows and not any(row[1] for row in rows)
        validation[suffix] = dict(zip(('passed', 'failed', 'ignored'), map(sum, zip(*rows))))
        assert validation[suffix]['passed'] == expected
    minimal = (root / 'disjoint-order-minimal-check.log').read_text()
    assert 'Finished' in minimal and 'error:' not in minimal
    validation['no_default_features'] = 'compile check passed'
    negative = (root / 'disjoint-order-negative.log').read_text()
    assert 'test result: FAILED' in negative and 'assertion `left == right` failed' in negative
    assert 'separate_source_epochs_preserve_ordered_merge_observations' in negative
    validation['negative_control'] = 'Bypassing disjointness changes ordered exported witnesses in the prior source-epoch regression; the scalar record value remains equal.'

    fixture = read(root / 'disjoint-order-fixture.json')
    assert fixture == read(root / 'disjoint-order-non-sparse-fixture.json')
    checkpoint = fixture['checkpoint']
    assert checkpoint['global_observer'] is False and fixture['pending_tasks'] == 2
    assert checkpoint['stats']['rhs_completions'] == 0
    assert checkpoint['stats']['source_unions_while_pending'] == 1
    assert checkpoint['stats']['bound_rhs_accepts'] == 1
    assert fixture['ports']['stats']['pure_epoch_order_disjoint'] == 4
    assert fixture['ports']['stats']['pure_epoch_order_rejections'] == 0
    assert fixture['exact_final_state_and_ordered_bindings'] is True

    prior = read(root / 'queue-overlays-audit/results.json')['cases']['sum-bits']['lanes']
    audit = read(root / 'disjoint-order-audit/results.json')
    lanes = audit['cases']['sum-bits']['lanes']
    new = ('pure_epoch_order_refinements', 'pure_epoch_order_disjoint',
           'pure_epoch_frontier_roots', 'pure_epoch_frontier_checks',
           'pure_epoch_frontier_unknown', 'pure_epoch_frontier_conflicts')
    changed = ('membership_checks', 'pure_epoch_order_checks', 'pure_epoch_peak_visits',
               'pure_epoch_source_steps', 'scratch_growths')
    results = {}
    for name, lane in lanes.items():
        old = prior[name]
        assert lane['runs'] == 1428 and lane['hashes'] == old['hashes'] == lanes['pure_epochs']['hashes']
        comparable = copy.deepcopy(lane)
        stats = comparable['port_completion']['stats']
        previous = old['port_completion']['stats']
        entry = {'new_proof_counters': {key: stats.pop(key) for key in new},
                 'previous_proof_work': {key: previous[key] for key in changed},
                 'current_proof_work': {key: stats[key] for key in changed}}
        assert entry['new_proof_counters'] == dict(zip(new, (7, 3, 29, 29, 0, 4)))
        assert stats['pure_epoch_order_rejections'] == 4 and stats['pure_epoch_accepts'] == 0
        work = lane['scoped_executor']['stats']
        assert (work['query_completions'], work['rhs_completions']) == (6, 4)
        assert work['source_unions_while_pending'] == work['rhs_fact_births_while_pending'] == 0
        entry['additional_bake_work_events'] = sum(entry['new_proof_counters'][key] for key in
            ('pure_epoch_order_refinements', 'pure_epoch_frontier_roots', 'pure_epoch_frontier_checks'))
        entry['additional_bake_work_events'] += sum(stats[key] - previous[key] for key in changed
                                                    if key != 'pure_epoch_peak_visits')
        assert entry['additional_bake_work_events'] == 77
        for key in changed:
            stats[key] = previous[key]
        assert deterministic(comparable) == deterministic(old), (name, 'unexpected deterministic change')
        results[name] = entry

    allocator = read(root / 'disjoint-order-allocator-audit/results.json')
    allocations = {}
    keys = ('alloc_calls', 'realloc_calls', 'requested_bytes')
    for name, lane in allocator['cases']['sum-bits']['lanes'].items():
        assert deterministic(lane) == deterministic(lanes[name]), name
        now = read(root / f'disjoint-order-allocator-audit/sum-bits-{name}/report.json')
        old = read(root / f'queue-overlays-allocator-audit/sum-bits-{name}/report.json')
        allocations[name] = {stage: {key: now[stage][key] for key in keys}
                             for stage in ('setup_allocations', 'allocations')}
        deltas = {stage: {key: now[stage][key] - old[stage][key] for key in keys}
                  for stage in ('setup_allocations', 'allocations')}
        assert not any(deltas['setup_allocations'].values())
        assert deltas['allocations'] == dict(zip(keys, (3, 0, 132)))
        allocations[name]['delta_from_previous_same_lane'] = deltas

    result = {
        'scope': 'standalone Cell CPU; complete frontier proof for independent source epochs sharing operators',
        'previous_revision': '8e20df0c', 'runtime_sha256': audit['runtime_sha256'],
        'allocator_runtime_sha256': allocator['runtime_sha256'],
        'program_file_sha256': lanes['pure_epochs']['program_file_sha256'],
        'runs': 1428, 'hashes': lanes['pure_epochs']['hashes'], 'validation': validation,
        'same_operator_fixture': fixture, 'fixture_storage_configs_match': True,
        'exact_ordered_semantics_match': True,
        'main_workload_waits_and_all_nonproof_work_unchanged': True,
        'lanes': results, 'allocator_requests': allocations,
        'admitted_as_performance_improvement': False,
        'proof': 'The compiler-bounded pure RHS and shared wiring expose complete possible effects. Only a table conflict triggers refinement. Explicit source endpoints and birth keys/results must miss all retained old frontiers, as must every affected result at overlapping tables. The existing closure checks downstream uses; incomplete frontiers, legacy effects and exhausted budgets retain the wait. Source checks are cached only within one immutable proof; no persistent dependency index is added.',
        'limits': 'The positive fixture proves a larger admissible execution region, not a speedup. Three individually disjoint sites in sum-bits do not certify any of its four rejected batches. All ten main-workload waits remain and the proof adds work/allocations. One writer, source publication ownership and epoch-end joins remain. No elapsed-time or scaling admission; allocator diagnostics exclude parsing/export and native thread stacks.',
    }
    (output / 'disjoint-order-audit.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    collect(args.root, args.output)
