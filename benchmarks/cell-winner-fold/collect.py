#!/usr/bin/env python3
"""Validate saved winner-fold runs and allocator costs; no workload execution."""
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
        assert a[key] == b[key]
    clean = lambda r: {k: v for k, v in r['stage_spine']['stats'].items() if not k.endswith('_seconds')}
    assert clean(a) == clean(b)
    old, new = [r['query_workers']['stats'] for r in [a, b]]
    assert b['query_workers']['winner_ordering'] == 'input-depth-ordinal/v1'
    for key in ['answers', 'completion_headers', 'completion_binding_moves', 'point_reads',
                'entries', 'result_writes', 'frame_allocations', 'compiled_cell_code_bytes']:
        assert old[key] == new[key], key
    moved = old['deferred_winner_moves'] - new['deferred_winner_moves']
    assert moved == new['completion_headers'] + new['deferred_winner_moves']
    assert moved > 0
    result = {
        'program_sha256': b['program_sha256'], 'state_sha256': sha(after / 'state.json'),
        'runs': len(runs(b)),
        'run_signature_sha256': hashlib.sha256(json.dumps(runs(b)).encode()).hexdigest(),
        'report_sha256': {'before': sha(before / 'report.json'), 'after': sha(after / 'report.json')},
        'intermediate_winner_records_removed': moved,
        'intermediate_winner_payload_bytes_removed': moved * b['stage_spine']['query_winner_bytes'],
        'intermediate_winner_batches_removed': old['batch_buffers'] - new['batch_buffers'],
        'deferred_winner_moves_before_after': [old['deferred_winner_moves'], new['deferred_winner_moves']],
        'batch_buffers_before_after': [old['batch_buffers'], new['batch_buffers']],
        'comparison_counts_NOT_same_scope': {
            'old_ordinal_sort_only': old['winner_order_comparisons'],
            'new_fused_key_depth_ordinal_sort': new['winner_order_comparisons'],
        },
        'residual_binding_moves_unchanged': new['completion_binding_moves'],
        'spine_bindings_unchanged': b['stage_spine']['stats']['bindings'],
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
    assert before['commit'] == 'c8d0584b'
    for name, digest in before['binaries'].items():
        assert sha(root / name) == digest
    checks = read(root / 'checks/checks.json')
    assert checks['baseline_commit'] == before['commit']
    assert checks['binaries']['baseline'] == sha(root / 'runtime-before')
    assert checks['binaries']['candidate'] == sha(root / 'runtime-after')
    assert checks['semantic_acceptance']['status'] == 'pass'
    result = {
        'scope': 'Standalone Cell CPU; one source-ordinal-aware winner selection. '
                 'Short work/allocator checks, not a timing result or native Raytrace proof.',
        'baseline': before,
        'binaries_after': {name: sha(root / name) for name in
            ['runtime-after', 'query-prefix-after', 'runtime-alloc-after']},
        'semantic_acceptance': checks['semantic_acceptance'],
        'cases': {},
        'comparisons': {'ray-prefix': compare(root / 'prefix-before', root / 'prefix-after')},
        'limits': 'Removed records moved owned Instances and cursors, not deep copies of slot values. '
                  'Bytes are cumulative removed intermediate payload, not allocator savings or peak memory. '
                  'Allocator costs measure the entire execute. The old counter omitted its second key sort; '
                  'comparison counts and historical Work scores cannot prove cross-version savings. '
                  'Residual merging, sorted input/depth selection and per-source error ordering remain.',
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
        ['intermediate_winner_records_removed', 'intermediate_winner_batches_removed', 'allocation_delta']}
        for name, row in result['comparisons'].items()}, indent=2))


if __name__ == '__main__':
    main()
