#!/usr/bin/env python3
"""Verify overlapping completion epochs, ordered semantics and retained costs."""
import argparse
import copy
import json
from pathlib import Path
import re


def read(path):
    return json.loads(path.read_text())


def deterministic(value):
    if isinstance(value, dict):
        return {k: deterministic(v) for k, v in value.items()
                if k not in ('worker_tasks', 'worker_candidates', 'observed') and not k.endswith('_seconds')}
    if isinstance(value, list):
        return [deterministic(v) for v in value]
    return value


def collect(root, output):
    validation = {}
    probes = ('an_effective_union_commits_while_a_snapshot_reader_is_held',
              'a_reader_panic_joins_workers_and_restores_committed_overlays')
    for suffix in ('workspace-tests', 'tests', 'non-sparse-tests', 'layer-tests', 'layer-non-sparse-tests'):
        log = (root / f'overlap-epochs-{suffix}.log').read_text()
        assert 'test result: FAILED' not in log
        for test in probes:
            assert f'{test} ... ok' in log, (suffix, test)
        if suffix in ('workspace-tests', 'layer-tests', 'layer-non-sparse-tests'):
            assert 'parallel_guard_dispatch_cannot_hide_preparation_from_bake_credit ... ok' in log
        if suffix == 'workspace-tests':
            for test in ('snapshots_move_bases_and_copy_only_written_slots',
                         'retired_nodes_remain_in_the_snapshot_only_until_readers_join',
                         'snapshot_roots_stay_fixed_while_live_roots_follow_new_unions'):
                assert f'{test} ... ok' in log
        rows = [tuple(map(int, row)) for row in re.findall(
            r'test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored', log)]
        assert rows and not any(row[1] for row in rows)
        validation[suffix] = dict(zip(('passed', 'failed', 'ignored'), map(sum, zip(*rows))))
    minimal = (root / 'overlap-epochs-minimal-check.log').read_text()
    assert 'Finished' in minimal and 'error:' not in minimal
    validation['no_default_features'] = 'compile check passed'
    negative = (root / 'overlap-epochs-negative-join.log').read_text()
    assert 'test result: FAILED' in negative and 'overlap probe timed out' in negative
    validation['negative_control'] = 'Waiting for every reader result before committing cannot release the held second reader.'

    prior = read(root / 'direct-guards-final-audit/results.json')['cases']['sum-bits']['lanes']
    audit = read(root / 'overlap-epochs-final-audit/results.json')
    lanes = audit['cases']['sum-bits']['lanes']
    mapping = {'pure_epochs': 'pure_epochs', 'batch_two': 'batch_two',
               'overlap_two': 'batch_two', 'overlap_four': 'batch_four', 'overlap_small': 'batch_small'}
    results = {}
    for name, lane in lanes.items():
        old = prior[mapping[name]]
        assert lane['runs'] == 1428 and lane['hashes'] == old['hashes'] == lanes['pure_epochs']['hashes']
        comparable = copy.deepcopy(lane)
        batch = comparable['stable_ports']['completion_batches']
        entry = {}
        if batch['enabled']:
            overlap = batch.pop('overlap')
            entry['overlap'] = overlap
            if name.startswith('overlap_'):
                assert overlap['enabled']
                comparable['args'].remove('--overlap-completion')
                stats = overlap['stats']
                work = batch['stats']
                assert stats['epochs'] == work['dispatches'] > 0
                assert stats['base_snapshots'] == 4 * stats['epochs']
                assert stats['channel_builds'] == stats['epochs']
                assert stats['task_spawns'] == work['prepared_tasks'] == stats['channel_receives']
                assert stats['row_handle_clones'] == work['committed_tasks']
                assert stats['reader_activity_updates'] == 2 * stats['task_spawns']
                for key, value in stats['overlay'].items():
                    assert value == sum(layer[key] for layer in stats['layers'].values()), key
                assert stats['layers']['parents']['copied_units'] == stats['layers']['nodes']['copied_units'] == 0
                assert stats['layers']['components']['copied_units'] > 0
                assert stats['layers']['queues']['copied_units'] > 0
                inventory = comparable['cell_ownership']['inventory']
                before = old['cell_ownership']['inventory']['allocated_signal_slots']
                after = inventory['allocated_signal_slots']
                assert after <= before
                entry['signal_capacity'] = {'before': before, 'after': after,
                    'meaning': 'Cloning touched signal vectors drops spare capacity; not a work saving.'}
                inventory['allocated_signal_slots'] = before
                entry['batch_scratch'] = {key: work[key] for key in ('scratch_allocations', 'scratch_bytes_requested')}
                for key in entry['batch_scratch']:
                    work[key] = old['stable_ports']['completion_batches']['stats'][key]
            else:
                assert overlap == {'enabled': False}
        assert deterministic(comparable) == deterministic(old), (name, 'unexpected deterministic change')
        results[name] = entry

    alloc_root = root / 'overlap-epochs-allocator-audit'
    allocator = read(alloc_root / 'results.json')
    allocations = {}
    for name, lane in allocator['cases']['sum-bits']['lanes'].items():
        assert deterministic(lane) == deterministic(lanes[name]), name
        report = read(alloc_root / f'sum-bits-{name}/report.json')
        allocations[name] = {stage: report[stage] for stage in ('setup_allocations', 'allocations')}
    for name, report in allocations.items():
        for baseline in ('pure_epochs', 'batch_two'):
            report[f'delta_from_{baseline}'] = {
                stage: {key: report[stage][key] - allocations[baseline][stage][key]
                        for key in ('alloc_calls', 'realloc_calls', 'requested_bytes')}
                for stage in ('setup_allocations', 'allocations')
            }
    result = {
        'scope': 'standalone Cell CPU; real snapshot readers overlap ordered coordinator commits',
        'previous_revision': '6578af2b', 'runtime_sha256': audit['runtime_sha256'],
        'allocator_runtime_sha256': allocator['runtime_sha256'],
        'program_file_sha256': lanes['pure_epochs']['program_file_sha256'],
        'runs': 1428, 'hashes': lanes['pure_epochs']['hashes'], 'validation': validation,
        'exact_ordered_semantics_match': True,
        'guard_work_source_waits_and_committed_effects_unchanged': True,
        'lanes': results, 'allocator_requests': allocations,
        'admitted_as_performance_improvement': False,
        'proof': 'Immutable moved bases isolate readers; coordinator overlays retain current state. Shared input-class certificates reject stale suffixes; liveness and queue order are rechecked. A held-reader gate requires an effective union before the reader can finish. Unwinding joins readers and merges overlays before retry.',
        'limits': 'One ordered writer and an epoch-end join remain; six query and four RHS waits persist. Observed active-reader counts are sampled at union entry, not a timing or scaling measure. Snapshot handles, copies, channels and merges are additional costs. Allocator requests exclude parsing/export and native thread stacks.',
    }
    (output / 'overlap-epochs-audit.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    collect(args.root, args.output)
