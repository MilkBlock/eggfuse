#!/usr/bin/env python3
"""Verify grouped snapshot readers and direct ordered result delivery."""
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
    for suffix in ('workspace-tests', 'tests', 'non-sparse-tests'):
        log = (root / f'slot-delivery-{suffix}.log').read_text()
        assert 'test result: FAILED' not in log
        for test in ('an_effective_union_commits_while_a_snapshot_reader_is_held',
                     'a_reader_panic_joins_workers_and_restores_committed_overlays',
                     'a_first_reader_panic_abandons_its_slots_and_releases_the_coordinator'):
            assert f'{test} ... ok' in log, (suffix, test)
        if suffix == 'workspace-tests':
            assert 'parallel_guard_dispatch_cannot_hide_preparation_from_bake_credit ... ok' in log
        rows = [tuple(map(int, row)) for row in re.findall(
            r'test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored', log)]
        assert rows and not any(row[1] for row in rows)
        validation[suffix] = dict(zip(('passed', 'failed', 'ignored'), map(sum, zip(*rows))))
    minimal = (root / 'slot-delivery-minimal-check.log').read_text()
    assert 'Finished' in minimal and 'error:' not in minimal
    validation['no_default_features'] = 'compile check passed'
    negative = (root / 'slot-delivery-negative-abandon.log').read_text()
    assert 'test result: FAILED' in negative and 'an abandoned first slot must release the coordinator' in negative
    validation['negative_control'] = 'Leaving unfilled slots on lane unwind prevents coordinator recovery; the bounded fixture fails.'

    prior = read(root / 'immutable-signals-audit/results.json')['cases']['sum-bits']['lanes']
    audit = read(root / 'slot-delivery-audit/results.json')
    lanes = audit['cases']['sum-bits']['lanes']
    results = {}
    new_fields = ('projected_tasks', 'input_buffer_allocations', 'input_buffer_bytes', 'activity_allocations',
                  'slot_publications', 'slot_abandons', 'slot_collection_reads', 'ordered_slot_reads')
    changed_fields = ('task_spawns', 'reader_activity_updates', 'channel_builds', 'channel_receives')
    for name, lane in lanes.items():
        old = prior[name]
        assert lane['runs'] == 1428 and lane['hashes'] == old['hashes'] == lanes['pure_epochs']['hashes']
        comparable = copy.deepcopy(lane)
        batch = comparable['stable_ports']['completion_batches']
        entry = {}
        if batch['enabled'] and batch['overlap']['enabled']:
            overlap = batch['overlap']
            stats = overlap['stats']
            old_overlap = old['stable_ports']['completion_batches']['overlap']
            prepared = batch['stats']['prepared_tasks']
            assert stats['projected_tasks'] == stats['slot_publications'] == stats['slot_collection_reads'] == prepared
            assert stats['slot_abandons'] == stats['channel_builds'] == stats['channel_receives'] == 0
            assert stats['ordered_slot_reads'] == batch['stats']['committed_tasks']
            assert stats['input_buffer_allocations'] == stats['epochs']
            assert stats['activity_allocations'] == 1
            assert stats['reader_activity_updates'] == 2 * stats['task_spawns']
            workers = int(lane['args'][lane['args'].index('--guard-workers') + 1])
            assert stats['epochs'] * 2 <= stats['task_spawns'] <= stats['epochs'] * workers
            assert stats['task_spawns'] < old_overlap['stats']['task_spawns'] == prepared
            entry['new_delivery_work'] = {key: stats.pop(key) for key in new_fields}
            entry['previous_dispatch'] = {key: old_overlap['stats'][key] for key in changed_fields}
            entry['current_dispatch'] = {key: stats[key] for key in changed_fields}
            entry['retained_overlay_work'] = stats['overlay']
            entry['result_buffer_bytes'] = stats['result_buffer_bytes']
            for key in changed_fields:
                stats[key] = old_overlap['stats'][key]
            assert overlap['scope'] == 'immutable epoch bases with coordinator write overlays; grouped readers publish directly to ordered result slots'
            overlap['scope'] = old_overlap['scope']
        assert deterministic(comparable) == deterministic(old), (name, 'unexpected semantic or work change')
        results[name] = entry

    allocator = read(root / 'slot-delivery-allocator-audit/results.json')
    allocations = {}
    keys = ('alloc_calls', 'realloc_calls', 'requested_bytes')
    stages = ('setup_allocations', 'allocations')
    for name, lane in allocator['cases']['sum-bits']['lanes'].items():
        assert deterministic(lane) == deterministic(lanes[name]), name
        now = read(root / f'slot-delivery-allocator-audit/sum-bits-{name}/report.json')
        old = read(root / f'immutable-signals-allocator-audit/sum-bits-{name}/report.json')
        allocations[name] = {stage: now[stage] for stage in stages}
        allocations[name]['delta_from_previous_same_lane'] = {
            stage: {key: now[stage][key] - old[stage][key] for key in keys} for stage in stages}
        assert all(value == 0 for value in allocations[name]['delta_from_previous_same_lane']['setup_allocations'].values())
    for name, report in allocations.items():
        for baseline in ('pure_epochs', 'batch_two'):
            report[f'delta_from_current_{baseline}'] = {
                stage: {key: report[stage][key] - allocations[baseline][stage][key] for key in keys} for stage in stages}
    for name in ('pure_epochs', 'batch_two'):
        assert all(value == 0 for value in allocations[name]['delta_from_previous_same_lane']['allocations'].values())
    assert allocations['overlap_two']['delta_from_previous_same_lane']['allocations']['alloc_calls'] < 0
    assert allocations['overlap_two']['delta_from_current_batch_two']['allocations']['alloc_calls'] > 0
    result = {
        'scope': 'standalone Cell CPU; grouped snapshot readers publish direct ordered result slots',
        'previous_revision': 'db2d2929', 'runtime_sha256': audit['runtime_sha256'],
        'allocator_runtime_sha256': allocator['runtime_sha256'],
        'program_file_sha256': lanes['pure_epochs']['program_file_sha256'],
        'runs': 1428, 'hashes': lanes['pure_epochs']['hashes'], 'validation': validation,
        'exact_ordered_semantics_match': True,
        'guard_queue_overlay_source_wait_and_committed_effect_work_unchanged': True,
        'lanes': results, 'allocator_requests': allocations,
        'admitted_as_performance_improvement': False,
        'proof': 'Compiler-certified immutable read windows permit strided groups. One-time slots publish results without copying answer payloads; coordinator selection and commits retain source order. Each lane abandons all unfilled positions on unwind, releasing waiters before scoped panic propagation and overlay restoration. Held-reader and both panic-retry gates pass.',
        'limits': 'No source wait or ordered writer is removed; queue copies and epoch-end joins remain. Grouping can reduce load balancing flexibility. Active-reader samples now count unfinished lanes and are not comparable utilization measures. Logical slot operation counts and one allocator execution are not elapsed-time or scaling evidence; parsing/export and native thread stacks are excluded.',
    }
    (output / 'slot-delivery-audit.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    collect(args.root, args.output)
