#!/usr/bin/env python3
"""Audit actual worker dispatch, extra work and ordered semantics; no timing gate."""
import argparse
import copy
import json
from pathlib import Path
import re


def read(path):
    return json.loads(path.read_text())


def collect(root, output):
    validation = {}
    for suffix in ('workspace-tests', 'tests', 'non-sparse-tests'):
        log = (root / f'parallel-guards-{suffix}.log').read_text()
        assert 'test result: FAILED' not in log
        rows = [tuple(map(int, row)) for row in re.findall(
            r'test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored', log)]
        assert rows and not any(row[1] for row in rows)
        for name in (
            'parallel_completion_preserves_partial_equalities_and_ordered_cascades',
            'small_candidate_batches_keep_the_serial_path_and_work_counts',
            'invalid_pool_configuration_does_not_change_graph_and_pool_is_reused',
        ):
            assert f'{name} ... ok' in log
        if 'wide_rounds_preserve_results_and_charge_descriptor_storage ... ok' not in log:
            wide = (root / f'parallel-guards-wide-{suffix}.log').read_text()
            assert 'wide_rounds_preserve_results_and_charge_descriptor_storage ... ok' in wide
            assert 'test result: ok. 1 passed; 0 failed' in wide
            rows.append((1, 0, 0))
        if suffix == 'workspace-tests' and 'parallel_guard_dispatch_cannot_hide_preparation_from_bake_credit ... ok' not in log:
            credit = (root / 'parallel-guards-credit-tests.log').read_text()
            assert 'parallel_guard_dispatch_cannot_hide_preparation_from_bake_credit ... ok' in credit
            assert 'test result: ok. 1 passed; 0 failed' in credit
            rows.append((1, 0, 0))
        validation[suffix] = dict(zip(('passed', 'failed', 'ignored'), map(sum, zip(*rows))))
    log = (root / 'parallel-guards-minimal-check.log').read_text()
    assert 'Finished' in log and 'error:' not in log
    validation['no_default_features'] = 'compile check passed'
    previous = read(root / 'read-guards-final-audit/results.json')['cases']['sum-bits']['lanes']['pure_epochs']
    audit = read(root / 'parallel-guards-final-audit/results.json')
    lanes = audit['cases']['sum-bits']['lanes']
    serial = lanes['pure_epochs']
    comparable = copy.deepcopy(serial)
    assert comparable['stable_ports'].pop('parallel_guards') == {'enabled': False}
    for key, value in previous.items():
        if key == 'stage_spine':
            for counter, n in value.items():
                if not counter.endswith('_seconds'):
                    assert comparable[key][counter] == n, (key, counter)
        else:
            assert comparable[key] == value, key
    results = {}
    for lane, value in lanes.items():
        assert value['hashes'] == previous['hashes'] and value['runs'] == 1428, lane
        if lane == 'pure_epochs':
            continue
        stable = value['stable_ports']
        parallel = stable['parallel_guards']
        stats = parallel['stats']
        extra = stats['speculative_guard_work']
        assert sum(stats['candidate_histogram']) == stats['candidate_batches']
        assert sum(parallel['worker_candidates']) == stats['prepared_candidates']
        assert stats['collected_results'] == stats['prepared_candidates']
        assert stats['below_grain_batches'] + stats['dispatched_batches'] == stats['candidate_batches']
        assert stats['prepared_live_guards'] <= stats['prepared_fact_lookups'] <= stats['prepared_candidates']
        assert stats['speculative_candidates'] == sum(stats[k] for k in (
            'speculative_pending_sites', 'speculative_local_conditions', 'speculative_key_candidates'))
        for counter, source in (
            ('port_reads', 'port_reads'), ('root_resolutions', 'port_reads'),
            ('key_field_comparisons', 'key_fields'),
        ):
            assert stable['stats'][counter] == serial['stable_ports']['stats'][counter] + extra[source], (lane, counter)
        assert stable['stats']['key_candidates'] == serial['stable_ports']['stats']['key_candidates'] + stats['speculative_key_candidates']
        for counter, source in (
            ('scalar_guards', 'scalar_guards'), ('equality_guards', 'equality_guards'),
            ('shared_symbol_guards', 'shared_symbol_guards'),
        ):
            assert stable['local_conditions']['stats'][counter] == serial['stable_ports']['local_conditions']['stats'][counter] + extra[source], (lane, counter)
        for counter, source in (('pending_sites', 'speculative_pending_sites'), ('condition_visits', 'speculative_local_conditions')):
            assert stable['local_conditions']['stats'][counter] == serial['stable_ports']['local_conditions']['stats'][counter] + stats[source], (lane, counter)
        for counter, n in serial['stable_ports']['stats'].items():
            if counter not in ('port_reads', 'root_resolutions', 'key_field_comparisons', 'key_candidates'):
                assert stable['stats'][counter] == n, (lane, counter)
        for counter, n in serial['stable_ports']['local_conditions']['stats'].items():
            if counter not in ('pending_sites', 'condition_visits', 'inactive_sites', 'operator_guards',
                               'scalar_guards', 'equality_guards', 'shared_symbol_guards'):
                assert stable['local_conditions']['stats'][counter] == n, (lane, counter)
        for key in ('stats', 'scoped_executor', 'scoped_completion', 'port_completion', 'maintenance', 'cell_ownership'):
            assert value[key] == serial[key], (lane, key)
        results[lane] = parallel
    # This is observed worker participation, not a wall-clock speedup claim.
    fine = results['two_workers_fine']
    assert fine['stats']['rounds'] > 0 and all(fine['worker_candidates'])
    allocator_root = root / 'parallel-guards-allocator-audit'
    allocator = read(allocator_root / 'results.json')
    allocations = {}
    for lane, value in allocator['cases']['sum-bits']['lanes'].items():
        assert value['hashes'] == serial['hashes'] and value['runs'] == 1428
        # Thread scheduling can change participation, not charged guard work.
        assert value['stable_ports']['stats'] == lanes[lane]['stable_ports']['stats']
        if lane != 'pure_epochs':
            assert value['stable_ports']['parallel_guards']['stats'] == results[lane]['stats']
        allocation_report = read(allocator_root / f'sum-bits-{lane}/report.json')
        allocations[lane] = {k: allocation_report[k] for k in ('setup_allocations', 'allocations')}
    for lane, measured in allocations.items():
        measured['delta_from_serial'] = {
            stage: {counter: measured[stage][counter] - allocations['pure_epochs'][stage][counter]
                    for counter in ('alloc_calls', 'realloc_calls', 'requested_bytes')}
            for stage in ('setup_allocations', 'allocations')
        }
    report = {
        'scope': 'standalone Cell CPU; persistent workers execute actual completion-candidate guards',
        'previous_revision': '94c2c0af',
        'runtime_sha256': audit['runtime_sha256'],
        'allocator_runtime_sha256': allocator['runtime_sha256'],
        'program_file_sha256': serial['program_file_sha256'],
        'runs': 1428, 'hashes': serial['hashes'],
        'exact_ordered_semantics_match': True,
        'disabled_deterministic_work_unchanged': True,
        'source_waits_and_committed_effects_unchanged': True,
        'extra_port_and_key_reads_fully_accounted': True,
        'admitted_as_performance_improvement': False,
        'validation': validation, 'lanes': results, 'allocator_requests': allocations,
        'limits': 'Per-candidate snapshot reads are parallel; one completion is committed at a time. Preparation, dispatch rounds, chunks, collection, scratch and speculative guards are counted. A separate diagnostic measures allocator requests during setup and execution, including the pool, but not native thread stacks or wall-clock contention. Worker distribution and allocator requests can depend on scheduling. No whole-executor parallelism, timing or stall-elimination claim.',
    }
    (output / 'parallel-guards-audit.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    collect(args.root, args.output)
