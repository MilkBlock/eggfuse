#!/usr/bin/env python3
"""Verify ordered fact overlays without cloning pending queue tables."""
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
    for suffix, expected in (('workspace-tests', 324), ('tests', 116), ('non-sparse-tests', 116)):
        log = (root / f'queue-overlays-{suffix}.log').read_text()
        assert 'test result: FAILED' not in log
        for test in ('an_effective_union_commits_while_a_snapshot_reader_is_held',
                     'a_reader_panic_joins_workers_and_restores_committed_overlays',
                     'a_first_reader_panic_abandons_its_slots_and_releases_the_coordinator'):
            assert f'{test} ... ok' in log, (suffix, test)
        if suffix == 'workspace-tests':
            for test in ('parallel_guard_dispatch_cannot_hide_preparation_from_bake_credit',
                         'snapshots_move_slot_storage_and_reject_in_epoch_mutation',
                         'queue_snapshot_preserves_membership_while_live_epochs_advance',
                         'epoch_queue_deltas_match_ordered_reference_through_reinsertion',
                         'requeued_early_keys_never_rescan_a_shadowed_base_prefix'):
                assert f'{test} ... ok' in log, test
        rows = [tuple(map(int, row)) for row in re.findall(
            r'test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored', log)]
        assert rows and not any(row[1] for row in rows)
        validation[suffix] = dict(zip(('passed', 'failed', 'ignored'), map(sum, zip(*rows))))
        assert validation[suffix]['passed'] == expected
    minimal = (root / 'queue-overlays-minimal-check.log').read_text()
    assert 'Finished' in minimal and 'error:' not in minimal
    validation['no_default_features'] = 'compile check passed'

    prior = read(root / 'slot-delivery-audit/results.json')['cases']['sum-bits']['lanes']
    audit = read(root / 'queue-overlays-audit/results.json')
    lanes = audit['cases']['sum-bits']['lanes']
    results = {}
    for name, lane in lanes.items():
        old = prior[name]
        assert lane['runs'] == 1428 and lane['hashes'] == old['hashes'] == lanes['pure_epochs']['hashes']
        comparable = copy.deepcopy(lane)
        queue = comparable['scoped_completion'].pop('queue_overlay')
        costs = queue['stats']
        assert set(costs) == {'table_probes', 'shadow_probes', 'live_probes', 'base_probes',
                             'base_head_reads', 'overlay_head_reads', 'table_activations',
                             'shadow_insert_attempts', 'changed_facts', 'live_inserts', 'live_removes',
                             'base_successor_ranges', 'base_successor_steps', 'merge_live_probes'}
        entry = {'queue_overlay': queue}
        batch = comparable['stable_ports']['completion_batches']
        if batch['enabled'] and batch['overlap']['enabled']:
            stats = batch['overlap']['stats']
            previous = old['stable_ports']['completion_batches']['overlap']['stats']
            for field, value in stats['overlay'].items():
                assert value == sum(layer[field] for layer in stats['layers'].values()), field
            assert stats['overlay']['copied_units'] == 0
            current_queue = stats['layers']['queues']
            old_queue = previous['layers']['queues']
            assert current_queue['copied_units'] == 0 < old_queue['copied_units']
            assert current_queue['writes'] == old_queue['writes']
            assert current_queue['merged_entries'] == costs['changed_facts'] == costs['merge_live_probes']
            assert costs['shadow_insert_attempts'] == costs['live_inserts'] + costs['live_removes']
            assert costs['table_activations'] <= old_queue['merged_entries']
            assert 0 < costs['changed_facts'] <= costs['shadow_insert_attempts'] <= current_queue['writes']
            assert costs['base_successor_ranges'] <= costs['shadow_insert_attempts']
            assert queue['retained_tables'] > 0 and queue['retained_shadow_slots'] > 0
            for layer in ('components', 'nodes', 'parents'):
                assert stats['layers'][layer] == previous['layers'][layer]
            entry['previous_queue_work'] = old_queue
            entry['current_queue_work'] = copy.deepcopy(current_queue)
            entry['current_all_layer_work'] = copy.deepcopy(stats['overlay'])
            entry['merge_units'] = 'Previous queues merged whole table slots; current queues merge unique shadowed facts. These counts are not comparable units.'
            stats['layers']['queues'] = old_queue
            stats['overlay'] = previous['overlay']
        else:
            assert not any(costs.values())
            assert queue['retained_tables'] == queue['retained_shadow_slots'] == queue['touched_table_capacity'] == 0
        assert deterministic(comparable) == deterministic(old), (name, 'unexpected semantic or work change')
        results[name] = entry

    allocator = read(root / 'queue-overlays-allocator-audit/results.json')
    allocations = {}
    keys = ('alloc_calls', 'realloc_calls', 'requested_bytes')
    stages = ('setup_allocations', 'allocations')
    for name, lane in allocator['cases']['sum-bits']['lanes'].items():
        assert deterministic(lane) == deterministic(lanes[name]), name
        now = read(root / f'queue-overlays-allocator-audit/sum-bits-{name}/report.json')
        old = read(root / f'slot-delivery-allocator-audit/sum-bits-{name}/report.json')
        allocations[name] = {stage: now[stage] for stage in stages}
        allocations[name]['delta_from_previous_same_lane'] = {
            stage: {key: now[stage][key] - old[stage][key] for key in keys} for stage in stages}
        # Use interval deltas so differences in binary/argument string lengths
        # before setup do not masquerade as retained execution memory.
        allocations[name]['additional_retained_execute_bytes'] = (
            now['allocations']['live_bytes_after'] - now['allocations']['live_bytes_before']
            - old['allocations']['live_bytes_after'] + old['allocations']['live_bytes_before'])
        assert all(value == 0 for value in allocations[name]['delta_from_previous_same_lane']['setup_allocations'].values())
    for name, report in allocations.items():
        for baseline in ('pure_epochs', 'batch_two'):
            report[f'delta_from_current_{baseline}'] = {
                stage: {key: report[stage][key] - allocations[baseline][stage][key] for key in keys} for stage in stages}
    for name in ('pure_epochs', 'batch_two'):
        assert all(value == 0 for value in allocations[name]['delta_from_previous_same_lane']['allocations'].values())
    result = {
        'scope': 'standalone Cell CPU; immutable pending queues with fact overlays and monotone base heads',
        'previous_revision': '0d46bc42', 'runtime_sha256': audit['runtime_sha256'],
        'allocator_runtime_sha256': allocator['runtime_sha256'],
        'program_file_sha256': lanes['pure_epochs']['program_file_sha256'],
        'runs': 1428, 'hashes': lanes['pure_epochs']['hashes'], 'validation': validation,
        'exact_ordered_semantics_match': True,
        'guard_dispatch_source_wait_and_committed_effect_work_unchanged': True,
        'all_four_snapshot_layers_copy_zero_values': True,
        'lanes': results, 'allocator_requests': allocations,
        'admitted_as_performance_improvement': False,
        'proof': 'The no-birth read window freezes original pending membership. A shadowed base key stays masked until join; reinsertion uses the live ordered overlay. The base head only advances, while minimum(base head, live head) preserves queue order. Per-fact source epochs, causes, liveness and both-endpoint invalidation retain their checks. Repeated-epoch differential and held-reader/panic-retry fixtures pass.',
        'accounting': 'Queue writes still count mutation API attempts including no-ops. Merge entries now count unique changed facts, not whole tables. Table/shadow/live/base probes count logical container operations, not internal comparisons. Growths count the delta directory, shadow sets and touched-table vector; internal BTree allocation is captured by the allocator build. changed_facts decomposes merged_entries and is not charged twice.',
        'limits': 'Additional hash/tree queries, ordered live edits, retained shadow capacities and merge work remain. One ordered writer, the epoch-end join, six query waits and four RHS waits remain. Zero copying and one allocator observation do not prove elapsed-time or scaling benefit. Parsing/export and native thread stacks are excluded.',
    }
    (output / 'queue-overlays-audit.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    collect(args.root, args.output)
