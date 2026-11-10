#!/usr/bin/env python3
"""Check saved query-instance handoff runs and allocator diagnostics; no timing."""
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


def compare(before, after, program):
    a, b = read(before / 'report.json'), read(after / 'report.json')
    p = read(program)
    assert a['program_sha256'] == b['program_sha256'] == p['sha256']
    assert sha(before / 'state.json') == sha(after / 'state.json')
    runs = lambda r: [[s[k] for k in RUN_FIELDS] for s in r['steps']]
    assert runs(a) == runs(b)
    assert a['stats'] == b['stats']
    assert a['key_lookup_calls'] == b['key_lookup_calls']
    x, y = a['stage_spine']['stats'], b['stage_spine']['stats']
    assert x['bindings_by_rule'] == y['bindings_by_rule']
    # The old Binding::matched collected one Slots buffer per returned match.
    # Derive its exact width from the checked source rule, never from hit ratios.
    widths = [sum(s['definition'] == 'query' for s in r['slots']) for r in p['recipe']['rules']]
    old_slots = sum(widths[int(r)] * n for r, n in x['bindings_by_rule'].items())
    old_allocs = sum(n for r, n in x['bindings_by_rule'].items() if widths[int(r)])
    assert old_slots == y['query_fragment_sealed_slots']
    assert a['local_context']['rules'].keys() == b['local_context']['rules'].keys()
    context_slots = 0
    for rule, stats in a['local_context']['rules'].items():
        other = b['local_context']['rules'][rule]
        assert stats['bindings'] == other['bindings']
        slots = widths[int(rule)] * stats['bindings']
        assert slots == other['terminal_input_slots']
        old_slots += slots
        old_allocs += stats['bindings'] if widths[int(rule)] else 0
        context_slots += slots
    new_slots = y['query_fragment_slots'] + context_slots
    assert new_slots >= old_slots
    result = {'program_sha256': sha(program), 'state_sha256': sha(after / 'state.json'),
        'runs': len(runs(b)), 'run_signature_sha256': hashlib.sha256(json.dumps(runs(b)).encode()).hexdigest(),
        'report_sha256': {'before': sha(before / 'report.json'), 'after': sha(after / 'report.json')},
        'key_lookup_calls': b['key_lookup_calls'],
        'derived_old_input_repack_allocations': old_allocs,
        'derived_old_input_value_moves': old_slots,
        'additional_early_slot_id_stores': new_slots - old_slots,
        'spine_candidates': y['query_fragment_frames'], 'spine_winners': y['bindings'],
        'spine_candidate_slot_capacity_bytes': y['query_fragment_capacity_bytes'],
        'spine_selected_slot_capacity_bytes': y['query_fragment_sealed_capacity_bytes'],
        'layout': {k: b['stage_spine'][k] for k in ['query_fragment_layout', 'query_winner_bytes',
                  'query_fragment_header_bytes', 'query_fragment_slot_bytes', 'query_value_bytes']},
        'compiled_cell_code_bytes': [r['query_workers']['stats']['compiled_cell_code_bytes'] for r in [a, b]]}
    if 'allocations' in a or 'allocations' in b:
        result['allocations'] = {label: r['allocations'] for label, r in [('before', a), ('after', b)]}
        result['setup_allocations'] = {label: r['setup_allocations'] for label, r in [('before', a), ('after', b)]}
        result['allocation_delta'] = {k: b['allocations'][k] - a['allocations'][k] for k in
            ['alloc_calls', 'realloc_calls', 'requested_bytes', 'peak_live_requested_bytes']}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('sum_program', type=Path)
    parser.add_argument('ray_program', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    root = args.root
    checks = read(root / 'checks/checks.json')
    before = read(root / 'before.json')
    for name, digest in before['binaries'].items():
        assert sha(root / name) == digest
    assert checks['baseline_commit'] == before['commit'][:8] == '8758d461'
    assert checks['binaries']['baseline'] == before['binaries']['runtime-before'] == sha(root / 'runtime-before')
    assert checks['binaries']['candidate'] == sha(root / 'runtime-after')
    assert checks['semantic_acceptance']['status'] == 'pass'
    result = {'scope': 'Standalone Cell CPU; same owned instance from query through winner selection to RHS. '
                       'Short work/allocator checks and Raytrace prefix, not a timing campaign.',
        'baseline': before, 'binaries_after': {k: sha(root / k) for k in
            ['runtime-after', 'runtime-alloc-after', 'query-prefix-after']},
        'semantic_acceptance': checks['semantic_acceptance'], 'cases': {}, 'comparisons': {},
        'limits': 'Input repack counts are derived from actual per-rule returned matches and checked input widths. '
                  'They are not all allocator savings: candidate width grows and winner containers change. '
                  'Allocator totals are measured separately; bytes are requested sizes, not RSS. '
                  'No speed credit for fragment coverage; RHS effects and result publication remain ordered.'}
    for name, case in checks['cases'].items():
        reference = case['lanes']['baseline']['hashes']
        assert all(v['hashes'] == reference for v in case['lanes'].values())
        result['cases'][name] = {'program_sha256': case['program_sha256'], 'lanes': {
            name: {k: row[k] for k in ['runs', 'hashes', 'report_sha256']} for name, row in case['lanes'].items()}}
    for workers in [1, 4]:
        result['comparisons'][f'sum-alloc-{workers}'] = compare(root / f'alloc-before-{workers}',
            root / f'alloc-after-{workers}', args.sum_program)
    result['comparisons']['ray-prefix'] = compare(root / 'prefix-before', root / 'prefix-after', args.ray_program)
    args.output.parent.mkdir(exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({name: {k: row[k] for k in ['derived_old_input_repack_allocations',
        'derived_old_input_value_moves', 'additional_early_slot_id_stores', 'allocation_delta'] if k in row}
        for name, row in result['comparisons'].items()}, indent=2))


if __name__ == '__main__':
    main()
