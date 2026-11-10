#!/usr/bin/env python3
"""Check saved shared Cell result exports and costs; never execute a workload."""
import argparse
import hashlib
import json
from pathlib import Path

RUN_FIELDS = ['ordinal', 'ruleset', 'path', 'iterations', 'epoch',
              'logical_matches', 'executed_bindings', 'changed']
OLD_COSTS = ['history_capture_reads', 'history_slots_written',
             'history_heap_frames', 'effect_slots_initialized']
NEW_COSTS = ['joint_history_checks', 'joint_history_frames',
             'joint_history_query_reads', 'joint_history_query_writes',
             'joint_output_reads']


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compare(before, after):
    a, b = read(before / 'report.json'), read(after / 'report.json')
    assert a['program_sha256'] == b['program_sha256']
    assert sha(before / 'state.json') == sha(after / 'state.json')
    runs = lambda r: [[s[k] for k in RUN_FIELDS] for s in r['steps']]
    assert runs(a) == runs(b)
    assert a['stats'] == b['stats']
    for key in ['key_lookup_calls', 'fact_decode_calls', 'fact_decode_ports']:
        assert a[key] == b[key], key
    old, new = a['stage_spine']['stats'], b['stage_spine']['stats']
    for key, value in old.items():
        if key not in OLD_COSTS + ['peak_cell_output_slots'] and not key.endswith('_seconds'):
            assert value == new[key], (key, value, new[key])
    assert b['stage_spine']['joint_result_storage'] == 'cell-results/v1'
    assert old['history_slots_written'] == new['history_slots_written'] + new['history_shared_slots']
    assert old['history_capture_reads'] == new['history_capture_reads'] + new['history_shared_slots']
    assert new['cell_output_receipts'] == new['cell_output_deliveries']
    assert a['stage_spine']['published_history_storage'] == b['stage_spine']['published_history_storage']
    costs = {key: [old[key], new[key]] for key in OLD_COSTS}
    costs.update({key: [0, new[key]] for key in NEW_COSTS})
    result = {
        'program_sha256': b['program_sha256'], 'state_sha256': sha(after / 'state.json'),
        'runs': len(runs(b)),
        'run_signature_sha256': hashlib.sha256(json.dumps(runs(b)).encode()).hexdigest(),
        'report_sha256': {'before': sha(before / 'report.json'), 'after': sha(after / 'report.json')},
        'result_storage_costs_before_after': costs,
        'result_storage_work_saved': sum(x - y for x, y in costs.values()),
        'shared_history_slots': new['history_shared_slots'],
        'new_shared_plan_bytes': b['stage_spine']['joint_result_plan_bytes'],
        'completion_record_bytes_after': b['stage_spine']['completion_record_bytes'],
        'published_history_storage_unchanged': b['stage_spine']['published_history_storage'],
        'pending_output_slots_peak_before_after': [old['peak_cell_output_slots'], new['peak_cell_output_slots']],
        'unchanged': {key: new[key] for key in ['history_allocations', 'history_result_reads',
            'effect_slot_probes', 'effect_slot_targets', 'cell_output_slot_reads', 'cell_output_deliveries',
            'output_registrations', 'cell_output_registrations', 'output_span_checks',
            'cell_output_span_seals', 'direct_publication_hash_probes']},
    }
    if 'allocations' in a:
        result['allocations'] = {'before': a['allocations'], 'after': b['allocations']}
        result['setup_allocations'] = {'before': a['setup_allocations'], 'after': b['setup_allocations']}
        result['allocation_delta'] = {key: b['allocations'][key] - a['allocations'][key]
            for key in ['alloc_calls', 'realloc_calls', 'requested_bytes', 'peak_live_requested_bytes']}
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    p.add_argument('output', type=Path)
    args = p.parse_args()
    root = args.root
    before = read(root / 'before.json')
    assert before['commit'].startswith('8f4e914f')
    for name, digest in before['binaries'].items():
        assert sha(root / name) == digest
    checks = read(root / 'checks/checks.json')
    assert checks['baseline_commit'] == '8f4e914f'
    assert checks['binaries']['baseline'] == sha(root / 'runtime-before')
    assert checks['binaries']['candidate'] == sha(root / 'runtime-after')
    assert checks['semantic_acceptance']['status'] == 'pass'
    result = {
        'scope': 'Standalone Cell CPU; RHS, existing history and Entry share actual result slots. '
                 'Short correctness/work/allocator checks, not timing or native Raytrace proof.',
        'baseline': before,
        'binaries_after': {name: sha(root / name) for name in
            ['runtime-after', 'query-prefix-after', 'runtime-alloc-after']},
        'semantic_acceptance': checks['semantic_acceptance'],
        'cases': {},
        'comparisons': {'ray-prefix': compare(root / 'prefix-before', root / 'prefix-after')},
        'limits': 'The equal-weight storage ledger is not time. Query reads/writes, new frame allocations, '
                  'initialization and publication owner lookups are charged. Coverage earns no credit. '
                  'Availability/retirement remain charged by existing output slot reads/deliveries; '
                  'mask diagnostics are subsets. Shared plan storage appears in allocator costs; '
                  'the publication mask reuses the unused arena offset. Raytrace prefix has no '
                  'captures and cannot establish full coverage.',
    }
    for name, case in checks['cases'].items():
        reference = case['lanes']['baseline']['hashes']
        assert all(row['hashes'] == reference for row in case['lanes'].values())
        result['cases'][name] = {'program_sha256': case['program_sha256'], 'lanes': {
            lane: {key: row[key] for key in ['runs', 'hashes', 'report_sha256']}
            for lane, row in case['lanes'].items()}}
    for workers in [1, 4]:
        result['comparisons'][f'sum-alloc-{workers}'] = compare(root / f'alloc-before-{workers}',
            root / f'alloc-after-{workers}')
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({name: {k: v for k, v in row.items() if k in
        ['result_storage_work_saved', 'shared_history_slots', 'new_shared_plan_bytes', 'allocation_delta']}
        for name, row in result['comparisons'].items()}, indent=2))


if __name__ == '__main__':
    main()
