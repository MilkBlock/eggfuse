#!/usr/bin/env python3
"""Check immutable signal bindings, tombstone retirement and their real costs."""
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
    for suffix in ('workspace-tests', 'tests', 'non-sparse-tests', 'cost-tests', 'cost-non-sparse-tests'):
        log = (root / f'immutable-signals-{suffix}.log').read_text()
        assert 'test result: FAILED' not in log
        for test in ('an_effective_union_commits_while_a_snapshot_reader_is_held',
                     'a_reader_panic_joins_workers_and_restores_committed_overlays'):
            assert f'{test} ... ok' in log, (suffix, test)
        if not suffix.startswith('cost-'):
            for test in ('stable_address_survives_representative_change_and_expires_on_recreation',
                         'component_retirement_cleans_previously_inactive_signal_slots'):
                assert f'{test} ... ok' in log, (suffix, test)
        if suffix == 'workspace-tests':
            assert 'whole_slot_retirement_keeps_nonclone_snapshot_without_copying ... ok' in log
        if suffix == 'workspace-tests' or suffix.startswith('cost-'):
            assert 'parallel_guard_dispatch_cannot_hide_preparation_from_bake_credit ... ok' in log
        rows = [tuple(map(int, row)) for row in re.findall(
            r'test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored', log)]
        assert rows and not any(row[1] for row in rows)
        validation[suffix] = dict(zip(('passed', 'failed', 'ignored'), map(sum, zip(*rows))))
    minimal = (root / 'immutable-signals-minimal-check.log').read_text()
    assert 'Finished' in minimal and 'error:' not in minimal
    validation['no_default_features'] = 'compile check passed'

    prior = read(root / 'overlap-epochs-final-audit/results.json')['cases']['sum-bits']['lanes']
    audit = read(root / 'immutable-signals-audit/results.json')
    lanes = audit['cases']['sum-bits']['lanes']
    results = {}
    for name, lane in lanes.items():
        old = prior[name]
        assert lane['runs'] == 1428 and lane['hashes'] == old['hashes'] == lanes['pure_epochs']['hashes']
        comparable = copy.deepcopy(lane)
        owner = comparable['cell_ownership']
        entry = {'ownership_roots_and_lifetime': {key: owner['stats'].pop(key) for key in
                 ('signal_root_queries', 'signal_parent_probes', 'component_lifetime_updates', 'component_lifetime_growths')}}
        work = entry['ownership_roots_and_lifetime']
        assert work['signal_parent_probes'] >= work['signal_root_queries'] > 0
        assert work['component_lifetime_updates'] == sum(owner['stats'][key] for key in
                                                        ('owned_births', 'adopted_existing', 'owned_retirements'))
        entry['new_route_attach_retire_root_queries'] = work['signal_root_queries'] - lane['port_completion']['stats']['output_reads']
        assert entry['new_route_attach_retire_root_queries'] > 0
        entry['component_lifetime_capacity_bytes'] = owner['inventory'].pop('component_lifetime_capacity_bytes')
        ports = comparable['stable_ports']
        entry['port_root_reads'] = ports['stats']['root_resolutions']
        entry['port_parent_probes'] = ports['stats'].pop('root_parent_probes')
        assert entry['port_parent_probes'] > entry['port_root_reads']
        parallel = ports['parallel_guards']
        if parallel['enabled']:
            assert parallel['stats']['speculative_guard_work'].pop('parent_probes') == 0
        batch = ports['completion_batches']
        if batch['enabled']:
            old_batch = old['stable_ports']['completion_batches']
            overlap = batch['overlap']
            prepared = batch['stats']['prepared_tasks']
            if not overlap['enabled']:
                # One extra u64 in each Task's worker-local guard counters.
                assert batch['stats']['scratch_bytes_requested'] == old_batch['stats']['scratch_bytes_requested'] + 8 * prepared
                batch['stats']['scratch_bytes_requested'] = old_batch['stats']['scratch_bytes_requested']
            else:
                stats = overlap['stats']
                previous = old_batch['overlap']['stats']
                entry['overlay_before'] = previous['overlay']
                entry['overlay_after'] = stats['overlay']
                entry['components_before'] = previous['layers']['components']
                entry['components_after'] = stats['layers']['components']
                components = entry['components_after']
                assert components['copied_units'] == 0
                assert 0 < components['writes'] == components['merged_entries'] < entry['components_before']['merged_entries']
                assert components['growths'] <= entry['components_before']['growths']
                for key, value in stats['overlay'].items():
                    assert value == sum(layer[key] for layer in stats['layers'].values()), key
                assert stats['overlay']['copied_units'] == stats['layers']['queues']['copied_units']
                assert stats['result_buffer_bytes'] == previous['result_buffer_bytes'] + 8 * prepared
                entry['result_buffer_bytes'] = stats['result_buffer_bytes']
                # All other layers and completion work must stay byte-for-byte equal.
                stats['overlay'] = previous['overlay']
                stats['layers']['components'] = previous['layers']['components']
                stats['result_buffer_bytes'] = previous['result_buffer_bytes']
                entry['signal_capacity_before'] = old['cell_ownership']['inventory']['allocated_signal_slots']
                entry['signal_capacity_after'] = owner['inventory']['allocated_signal_slots']
                assert entry['signal_capacity_after'] == lanes['pure_epochs']['cell_ownership']['inventory']['allocated_signal_slots']
                owner['inventory']['allocated_signal_slots'] = entry['signal_capacity_before']
        assert deterministic(comparable) == deterministic(old), (name, 'unexpected work or semantic change')
        results[name] = entry

    allocator = read(root / 'immutable-signals-allocator-audit/results.json')
    allocations = {}
    keys = ('alloc_calls', 'realloc_calls', 'requested_bytes')
    stages = ('setup_allocations', 'allocations')
    for name, lane in allocator['cases']['sum-bits']['lanes'].items():
        assert deterministic(lane) == deterministic(lanes[name]), name
        now = read(root / f'immutable-signals-allocator-audit/sum-bits-{name}/report.json')
        old = read(root / f'overlap-epochs-allocator-audit/sum-bits-{name}/report.json')
        allocations[name] = {stage: now[stage] for stage in stages}
        allocations[name]['delta_from_previous_same_lane'] = {
            stage: {key: now[stage][key] - old[stage][key] for key in keys} for stage in stages}
    for name, report in allocations.items():
        for baseline in ('pure_epochs', 'batch_two'):
            report[f'delta_from_current_{baseline}'] = {
                stage: {key: report[stage][key] - allocations[baseline][stage][key] for key in keys} for stage in stages}
    assert allocations['overlap_two']['delta_from_previous_same_lane']['allocations']['alloc_calls'] < 0
    assert allocations['overlap_two']['delta_from_current_batch_two']['allocations']['alloc_calls'] > 0
    result = {
        'scope': 'standalone Cell CPU; immutable signal bindings and coordinator-only lifetime counts',
        'previous_revision': 'c05e4cc2', 'runtime_sha256': audit['runtime_sha256'],
        'allocator_runtime_sha256': allocator['runtime_sha256'],
        'program_file_sha256': lanes['pure_epochs']['program_file_sha256'],
        'runs': 1428, 'hashes': lanes['pure_epochs']['hashes'], 'validation': validation,
        'exact_ordered_semantics_match': True,
        'old_guard_dispatch_boundary_and_source_wait_work_unchanged': True,
        'signal_union_rewrites_removed': lanes['pure_epochs']['cell_ownership']['stats']['signal_activations'],
        'lanes': results, 'allocator_requests': allocations,
        'admitted_as_performance_improvement': False,
        'proof': 'First-bound IDs remain stable and resolve through current or frozen Parents. Native routes are captured before the link; retirement removes current-root boundaries. Only the coordinator owns live counts; non-Clone component records can only be tombstoned during an epoch. Held-reader and panic-retry gates still pass.',
        'limits': 'No additional source wait is removed. Queues still copy, and channels, task dispatch, an ordered writer and epoch-end join remain. Parent probes are logical directory requests, not physical map accesses or timing; deeper binding walks are charged. Allocation counts are one diagnostic execution, excluding parsing/export and native thread stacks.',
    }
    (output / 'immutable-signals-audit.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    collect(args.root, args.output)
