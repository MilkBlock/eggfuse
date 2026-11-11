#!/usr/bin/env python3
"""Check same-instance constructor continuation, including added work/storage."""
import hashlib
import json
from pathlib import Path
import sys


def read(path):
    return json.loads(path.read_text())


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def check(root, prior, output):
    result = {'scope': 'standalone Cell CPU; work and semantic evidence, not timing',
              'control_commit': '8369a224', 'runtime_sha256': sha(root / 'runtime'),
              'control_runtime_sha256': sha(prior / 'runtime'), 'workloads': {}}
    steps = ('ordinal', 'ruleset', 'path', 'iterations', 'epoch',
             'logical_matches', 'executed_bindings', 'changed')
    for case in ('sum', 'ray'):
        a, b = [read(base / case / 'report.json') for base in (prior, root)]
        assert a['status'] == b['status'] == 'complete'
        assert a['program_sha256'] == b['program_sha256']
        state = sha(root / case / 'state.json')
        assert state == sha(prior / case / 'state.json')
        assert [[s[k] for k in steps] for s in a['steps']] == [[s[k] for k in steps] for s in b['steps']]
        for key, value in a['stats'].items():
            if not key.startswith('constructor_prepared_'):
                assert value == b['stats'][key], (case, key)
        fragment_storage = ('query_fragment_capacity_bytes', 'query_fragment_sealed_capacity_bytes',
                            'query_fragment_sealed_slots', 'query_fragment_slots')
        for key, value in a['stage_spine']['stats'].items():
            if not key.endswith('_seconds') and key not in fragment_storage:
                assert value == b['stage_spine']['stats'][key], (case, 'stage_spine', key)
        for key in ('maintenance', 'free_join', 'entry_schedule', 'known_results',
                    'neighbor_context', 'indexed_columns', 'repair_ports', 'multi_stage',
                    'cell_ownership', 'live_cells'):
            assert a[key] == b[key], (case, key)
        before = a['query_workers']['stats']['execution']['constructor']
        after = b['query_workers']['stats']['execution']['constructor']
        prefix = {k: v for k, v in b['stats'].items() if k.startswith('constructor_prefix_')}
        assert prefix['constructor_prefix_frames'] > 0
        assert prefix['constructor_prefix_rejected'] == prefix['constructor_prefix_discarded_slots'] == 0
        extra_probes = after['lookups'] - before['lookups']
        removed_source = (prefix['constructor_prefix_operations']
                          + b['stats']['constructor_prepared_accepted']
                          - a['stats']['constructor_prepared_accepted'])
        assert b['key_lookup_calls'] - a['key_lookup_calls'] == extra_probes - removed_source
        assert after['lookups'] == after['hits'] + after['misses']
        old_boundaries = a['cell_execution']['runtime']['stats']['boundaries']
        new_boundaries = b['cell_execution']['runtime']['stats']['boundaries']
        assert old_boundaries[1:] == new_boundaries[1:]
        assert b['cell_execution']['rhs_owner_bytes'] == a['cell_execution']['rhs_owner_bytes']
        delta = read(root / f'{case}-work.json')
        result['workloads'][case] = {
            'program_sha256': b['program_sha256'], 'state_sha256': state, 'runs': len(b['steps']),
            'exact_final_state_and_ordered_run_summaries': True,
            'original_logical_graph_work_unchanged': True,
            'prefix_source_work': prefix,
            'constructor_preparation_before': before, 'constructor_preparation_after': after,
            'additional_worker_probes': extra_probes, 'additional_source_lookups_removed': removed_source,
            'total_key_lookups': [a['key_lookup_calls'], b['key_lookup_calls']],
            'constructor_boundaries': [old_boundaries[0], new_boundaries[0]],
            'other_boundaries': new_boundaries[1:],
            'instance_header_bytes': [a['query_workers']['instance_header_bytes'], b['query_workers']['instance_header_bytes']],
            'execution_header_bytes': b['cell_execution']['rhs_owner_bytes'],
            'compiled_payload_bytes': [a['cell_execution']['compiled_payload_bytes'], b['cell_execution']['compiled_payload_bytes']],
            'fragment_storage': {k: [a['stage_spine']['stats'][k], b['stage_spine']['stats'][k]] for k in fragment_storage},
            'plan': b['cell_execution']['constructor_preparation'],
            'net_saved_uncalibrated_operations': delta['net_saved_operations'],
            'work_ledger_sha256': sha(root / f'{case}-work.json'),
        }
    acceptance = read(root / 'semantic-acceptance.json')
    assert acceptance['status'] == 'pass'
    assert acceptance['input_sha256']['cpu_values'] == result['workloads']['sum']['state_sha256']
    result['native_sum_acceptance'] = {'status': 'pass', 'sha256': sha(root / 'semantic-acceptance.json')}
    output.write_text(json.dumps(result, indent=2) + '\n')
    print('same final states, Run summaries and logical effects; added work/storage recorded')


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    check(*map(Path, sys.argv[1:]))
