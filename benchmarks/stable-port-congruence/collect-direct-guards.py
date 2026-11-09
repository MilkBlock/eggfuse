#!/usr/bin/env python3
"""Audit direct stable-node reads against the frozen completion-batch revision."""
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
    for suffix in ('workspace-tests', 'tests', 'non-sparse-tests'):
        log = (root / f'direct-guards-{suffix}.log').read_text()
        assert 'test result: FAILED' not in log
        for test in ('direct_worker_reads_skip_preparation_and_unused_candidates',
                     'a_new_read_borrow_observes_aliases_and_rejects_retired_instances',
                     'a_bridged_child_union_invalidates_its_dependent_prefetched_suffix',
                     'deleted_producer_retains_consumers_across_a_late_union'):
            assert f'{test} ... ok' in log, (suffix, test)
        rows = [tuple(map(int, row)) for row in re.findall(
            r'test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored', log)]
        assert rows and not any(row[1] for row in rows)
        validation[suffix] = dict(zip(('passed', 'failed', 'ignored'), map(sum, zip(*rows))))
    minimal = (root / 'direct-guards-minimal-check.log').read_text()
    assert 'Finished' in minimal and 'error:' not in minimal
    validation['no_default_features'] = 'compile check passed'
    negative = (root / 'direct-guards-negative-retirement.log').read_text()
    assert 'test result: FAILED' in negative
    assert 'assertion failed: g.stable_key_guard(fact, table, &key).unwrap().is_none()' in negative
    validation['retirement_negative_control'] = 'Omitting directory removal exposes a deleted fact as a live guard.'

    previous = read(root / 'completion-batches-final-audit/results.json')
    audit = read(root / 'direct-guards-final-audit/results.json')
    old_lanes = previous['cases']['sum-bits']['lanes']
    lanes = audit['cases']['sum-bits']['lanes']
    results = {}
    changed_batch = ('prepared_candidates', 'pending_probes', 'candidate_fact_lookups',
                     'scratch_allocations', 'scratch_bytes_requested')
    directory_fields = ('node_lookups', 'node_retirement_probes', 'nodes_retired')
    for name, lane in lanes.items():
        old = old_lanes[name]
        assert lane['runs'] == old['runs'] == 1428
        assert lane['hashes'] == old['hashes'] == lanes['pure_epochs']['hashes']
        comparable = copy.deepcopy(lane)
        stable = comparable['stable_ports']
        directory = {key: stable['stats'].pop(key) for key in directory_fields}
        assert directory['node_lookups'] > 0
        assert (stable['stats']['rows_installed'] - directory['nodes_retired']
                == stable['live_stable_nodes'])
        if stable['parallel_guards']['enabled']:
            assert stable['parallel_guards']['stats']['speculative_guard_work'].pop('node_lookups') == 0
        result = {'directory_work': directory}
        if name.startswith('batch_'):
            batch = stable['completion_batches']['stats']
            before = old['stable_ports']['completion_batches']['stats']
            assert batch.pop('candidate_positions') == before['prepared_candidates']
            assert batch['prepared_candidates'] == 0
            assert batch['candidate_fact_lookups'] == batch['guard_candidates']
            assert batch['pending_probes'] <= batch['candidate_fact_lookups']
            for key in changed_batch:
                assert batch[key] < before[key], (name, key, batch[key], before[key])
            result['changed_batch_work'] = {
                key: {'before': before[key], 'after': batch[key], 'saved': before[key] - batch[key]}
                for key in changed_batch
            }
            for key in changed_batch:
                batch[key] = before[key]
            result['batches'] = lane['stable_ports']['completion_batches']
        assert deterministic(comparable) == deterministic(old), (name, 'unaccounted deterministic change')
        results[name] = result

    allocation_root = root / 'direct-guards-allocator-audit'
    allocator = read(allocation_root / 'results.json')
    allocations = {}
    for name, lane in allocator['cases']['sum-bits']['lanes'].items():
        assert deterministic(lane) == deterministic(lanes[name]), name
        report = read(allocation_root / f'sum-bits-{name}/report.json')
        old_report = read(root / 'completion-batches-allocator-audit' / f'sum-bits-{name}/report.json')
        allocations[name] = {stage: report[stage] for stage in ('setup_allocations', 'allocations')}
        allocations[name]['delta_from_previous_revision'] = {
            stage: {key: report[stage][key] - old_report[stage][key]
                    for key in ('alloc_calls', 'realloc_calls', 'requested_bytes')}
            for stage in ('setup_allocations', 'allocations')
        }
    for value in allocations.values():
        value['delta_from_current_serial'] = {
            stage: {key: value[stage][key] - allocations['pure_epochs'][stage][key]
                    for key in ('alloc_calls', 'realloc_calls', 'requested_bytes')}
            for stage in ('setup_allocations', 'allocations')
        }
    result = {
        'scope': 'standalone Cell CPU; authoritative stable-node directory and lazy worker reads',
        'previous_revision': 'c498415a',
        'runtime_sha256': audit['runtime_sha256'],
        'allocator_runtime_sha256': allocator['runtime_sha256'],
        'program_file_sha256': lanes['pure_epochs']['program_file_sha256'],
        'runs': 1428, 'hashes': lanes['pure_epochs']['hashes'], 'validation': validation,
        'all_other_deterministic_counters_unchanged': True,
        'exact_ordered_semantics_match': True,
        'source_waits_and_committed_effects_unchanged': True,
        'lanes': results, 'allocator_requests': allocations,
        'admitted_as_performance_improvement': False,
        'proof': 'Stable nodes have one authoritative owner; retirement removes identity entries. Workers borrow nodes, queue membership and typed guard code, returning disjoint answers and local work. Existing input-class certificates and ordered commits are unchanged.',
        'limits': 'No Graph mutation overlaps worker reads; source waits and serial commits remain. A fact-keyed hash directory replaces Cell field ownership, adding lookup/lifetime costs. Allocator requests exclude parsing/export and native stacks. No timing or scaling admission.',
    }
    (output / 'direct-guards-audit.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    collect(args.root, args.output)
