#!/usr/bin/env python3
"""Check input-class certificates and ordered multi-task reads, without timing admission."""
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
                if k not in ('worker_tasks', 'worker_candidates') and not k.endswith('_seconds')}
    if isinstance(value, list):
        return [deterministic(v) for v in value]
    return value


def collect(root, output):
    validation = {}
    names = (
        'same_sort_tasks_reuse_reads_across_result_unions',
        'pending_peers_can_become_survivors_and_retired_peers_are_rejected',
        'a_derived_input_alias_invalidates_prefetched_conditions',
        'an_absorbing_input_class_is_checked_even_when_its_root_number_survives',
        'a_new_earlier_child_task_preserves_independent_prefetched_reads',
        'a_bridged_child_union_invalidates_its_dependent_prefetched_suffix',
        'selective_batches_leave_unrelated_same_sort_completion_pending',
        'partial_multi_input_guards_and_recreated_facts_keep_their_lifetimes',
        'batch_configuration_is_bounded_and_requires_a_pool',
    )
    for suffix in ('workspace-tests', 'tests', 'non-sparse-tests'):
        log = (root / f'completion-batches-{suffix}.log').read_text()
        assert 'test result: FAILED' not in log
        for name in names:
            assert f'{name} ... ok' in log, (suffix, name)
        rows = [tuple(map(int, row)) for row in re.findall(
            r'test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored', log)]
        assert rows and not any(row[1] for row in rows)
        validation[suffix] = dict(zip(('passed', 'failed', 'ignored'), map(sum, zip(*rows))))
    minimal = (root / 'completion-batches-minimal-check.log').read_text()
    assert 'Finished' in minimal and 'error:' not in minimal
    validation['no_default_features'] = 'compile check passed'
    negative = (root / 'completion-batches-negative-input.log').read_text()
    assert 'test result: FAILED' in negative
    assert 'assertion `left == right` failed' in negative
    validation['negative_control'] = 'Removing input-class invalidation leaves duplicate H constructors in exact export.'
    bridge_negative = (root / 'completion-batches-negative-bridge.log').read_text()
    assert 'test result: FAILED' in bridge_negative and 'assertion `left == right` failed' in bridge_negative
    validation['bridge_negative_control'] = 'Omitting the child-union certificate leaves two H constructors instead of one.'
    old = read(root / 'parallel-guards-final-audit/results.json')['cases']['sum-bits']['lanes']
    audit = read(root / 'completion-batches-final-audit/results.json')
    lanes = audit['cases']['sum-bits']['lanes']
    for lane in ('pure_epochs', 'two_workers_fine'):
        value = copy.deepcopy(lanes[lane])
        assert value['stable_ports'].pop('completion_batches') == {'enabled': False}
        assert deterministic(value) == deterministic(old[lane]), lane
    serial = lanes['pure_epochs']
    results = {}
    for lane, value in lanes.items():
        assert value['hashes'] == serial['hashes'] == old['pure_epochs']['hashes']
        assert value['runs'] == 1428
        assert value['stats'] == serial['stats'], (lane, 'committed runtime effects')
        assert value['scoped_executor'] == serial['scoped_executor'], (lane, 'source waits')
        if not lane.startswith('batch_'):
            continue
        batches = value['stable_ports']['completion_batches']
        stats = batches['stats']
        assert stats['dispatches'] > 0 and stats['reused_after_union'] > 0
        assert stats['prepared_tasks'] == stats['committed_tasks'] + stats['unused_tasks']
        assert stats['prepared_tasks'] == stats['collected_tasks'] == sum(batches['worker_tasks'])
        assert stats['preparation_errors'] == 0
        guards = value['stable_ports']['parallel_guards']['stats']
        results[lane] = {
            'batches': batches,
            'total_pool_rounds': stats['dispatches'] + guards['rounds'],
            'fallback_candidate_rounds': guards['rounds'],
            'stable_port_work': value['stable_ports']['stats'],
            'local_condition_work': value['stable_ports']['local_conditions']['stats'],
            'scoped_queue_work': value['scoped_completion']['stats'],
        }
    assert results['batch_two']['batches']['stats'] == results['batch_four']['batches']['stats']
    allocation_root = root / 'completion-batches-allocator-audit'
    allocator = read(allocation_root / 'results.json')
    allocations = {}
    for lane, value in allocator['cases']['sum-bits']['lanes'].items():
        assert value['hashes'] == serial['hashes'] and value['runs'] == 1428
        assert deterministic(value) == deterministic(lanes[lane]), lane
        report = read(allocation_root / f'sum-bits-{lane}/report.json')
        allocations[lane] = {k: report[k] for k in ('setup_allocations', 'allocations')}
    for value in allocations.values():
        value['delta_from_serial'] = {
            stage: {key: value[stage][key] - allocations['pure_epochs'][stage][key]
                    for key in ('alloc_calls', 'realloc_calls', 'requested_bytes')}
            for stage in ('setup_allocations', 'allocations')
        }
    result = {
        'scope': 'standalone Cell CPU; real persistent workers across completion tasks',
        'previous_revision': '8c9c4fd8',
        'runtime_sha256': audit['runtime_sha256'],
        'allocator_runtime_sha256': allocator['runtime_sha256'],
        'program_file_sha256': serial['program_file_sha256'],
        'runs': 1428, 'hashes': serial['hashes'], 'validation': validation,
        'disabled_deterministic_work_unchanged': True,
        'exact_ordered_semantics_match': True,
        'source_waits_and_committed_effects_unchanged': True,
        'previous_fine_candidate_rounds': lanes['two_workers_fine']['stable_ports']['parallel_guards']['stats']['rounds'],
        'lanes': results, 'allocator_requests': allocations,
        'admitted_as_performance_improvement': False,
        'proof': 'Complete compiler key columns; snapshot candidate domains; both derived-union classes checked against future input classes; current peer liveness/pending and source order rechecked. New earlier pure constructor tasks run in serial order and certify their unions too. Legacy/opaque effects preempt the suffix.',
        'limits': 'No Graph mutation during worker reads; commits and source fences remain serial. Transient read sets and task preparation are new work, not persistent producer subscriptions. Counts include discarded work; allocator intervals include setup and execute but exclude native stacks, parsing and export. No timing or scaling admission.',
    }
    (output / 'completion-batches-audit.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    collect(args.root, args.output)
