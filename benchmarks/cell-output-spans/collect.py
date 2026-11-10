#!/usr/bin/env python3
"""Verify saved Cell output-span checks and costs; does not execute workloads."""
import argparse
import hashlib
import json
from pathlib import Path

RUN_FIELDS = ['ordinal', 'ruleset', 'path', 'iterations', 'epoch',
              'logical_matches', 'executed_bindings', 'changed']


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
        if not key.endswith('_seconds'):
            assert value == new[key], (key, value, new[key])
    assert b['stage_spine']['output_registration'] == 'cell-span/v1'
    sealed = new['cell_output_sealed_receipts']
    assert sealed > 0
    assert old['captured_anchors'] == new['output_registrations'] + sealed
    assert old['cell_output_receipts'] == new['cell_output_registrations'] + sealed
    assert new['cell_output_receipts'] == new['cell_output_deliveries']
    costs = {
        'output_registrations': [old['captured_anchors'], new['output_registrations']],
        'cell_output_registrations': [old['cell_output_receipts'], new['cell_output_registrations']],
        **{key: [0, new[key]] for key in
           ['cell_output_span_seals', 'output_span_checks', 'output_residual_dispatches']},
    }
    result = {
        'program_sha256': b['program_sha256'], 'state_sha256': sha(after / 'state.json'),
        'runs': len(runs(b)),
        'run_signature_sha256': hashlib.sha256(json.dumps(runs(b)).encode()).hexdigest(),
        'report_sha256': {'before': sha(before / 'report.json'), 'after': sha(after / 'report.json')},
        'registration_costs_before_after': costs,
        'registration_work_saved': sum(x - y for x, y in costs.values()),
        'sealed_receipts': sealed,
        'new_shared_registration_bytes': b['stage_spine']['effect_plan_registration_bytes'],
        'unchanged': {key: new[key] for key in ['effect_output_copies', 'effect_outputs_reused',
            'cell_output_slot_reads', 'cell_output_deliveries', 'history_capture_reads',
            'history_slots_written', 'direct_publication_hash_probes']},
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
    assert before['commit'].startswith('33f5fada')
    for name, digest in before['binaries'].items():
        assert sha(root / name) == digest
    checks = read(root / 'checks/checks.json')
    assert checks['baseline_commit'] == '33f5fada'
    assert checks['binaries']['baseline'] == sha(root / 'runtime-before')
    assert checks['binaries']['candidate'] == sha(root / 'runtime-after')
    assert checks['semantic_acceptance']['status'] == 'pass'
    result = {
        'scope': 'Standalone Cell CPU; Cell output spans replace per-output registration. '
                 'Short correctness/work/allocator checks, not timing or native Raytrace proof.',
        'baseline': before,
        'binaries_after': {name: sha(root / name) for name in
            ['runtime-after', 'query-prefix-after', 'runtime-alloc-after']},
        'semantic_acceptance': checks['semantic_acceptance'],
        'cases': {},
        'comparisons': {'ray-prefix': compare(root / 'prefix-before', root / 'prefix-after')},
        'limits': 'Registration work uses the Bake ledger operation weights, not nanoseconds. '
                  'Coverage is not rewarded. Receipt writes, legal-boundary delivery and history '
                  'remain charged. New shared plans allocate; allocator diagnostics are not timing.',
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
    print(json.dumps(result['comparisons'], indent=2))


if __name__ == '__main__':
    main()
