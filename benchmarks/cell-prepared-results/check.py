#!/usr/bin/env python3
"""Check transfer of worker results into their source Cell's result layout."""
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
              'control_commit': '356f0424', 'runtime_sha256': sha(root / 'runtime'),
              'control_runtime_sha256': sha(prior / 'runtime'), 'workloads': {}}
    step_fields = ('ordinal', 'ruleset', 'path', 'iterations', 'epoch',
                   'logical_matches', 'executed_bindings', 'changed')
    for case in ('sum', 'ray'):
        a, b = [read(base / case / 'report.json') for base in (prior, root)]
        assert a['status'] == b['status'] == 'complete'
        assert a['program_sha256'] == b['program_sha256']
        state = sha(root / case / 'state.json')
        assert state == sha(prior / case / 'state.json')
        assert [[s[k] for k in step_fields] for s in a['steps']] == [[s[k] for k in step_fields] for s in b['steps']]
        for key, value in a['stats'].items():
            if key != 'constructor_prefix_receipt_writes':
                assert value == b['stats'][key], (case, key, value, b['stats'][key])
        assert b['stats']['constructor_prefix_receipt_writes'] == 0
        for key in ('maintenance', 'free_join', 'entry_schedule', 'known_results',
                    'neighbor_context', 'indexed_columns', 'repair_ports', 'multi_stage',
                    'cell_ownership', 'live_cells', 'key_lookup_calls'):
            assert a[key] == b[key], (case, key)
        assert a['cell_execution']['runtime']['stats'] == b['cell_execution']['runtime']['stats']
        assert a['query_workers']['instance_header_bytes'] == b['query_workers']['instance_header_bytes']
        assert a['cell_execution']['rhs_owner_bytes'] == b['cell_execution']['rhs_owner_bytes']
        spine_differences = {k: [a['stage_spine']['stats'].get(k), v] for k, v in b['stage_spine']['stats'].items()
                             if not k.endswith('_seconds') and a['stage_spine']['stats'].get(k) != v}
        for k in spine_differences:
            assert k.startswith(('effect_', 'prepared_effect_')) or k in (
                'joint_scratch_growths', 'joint_scratch_growth_bytes'), (case, 'unexpected source work', k)
        assert b['stage_spine']['stats']['prepared_effect_buffer_moves'] > 0
        before, after = [r['query_workers']['stats']['execution']['constructor'] for r in (a, b)]
        for key in ('attempts', 'lookups', 'hits', 'misses', 'key_fields', 'prefix_slot_writes',
                    'prefix_slot_growths', 'prefix_capacity_bytes', 'prefix_instances'):
            assert before[key] == after[key], (case, key)
        removed_writes = (before['result_writes'] + a['stats']['constructor_prefix_receipt_writes']
                          - after['result_writes'] - b['stats']['constructor_prefix_receipt_writes']
                          - b['stage_spine']['stats']['prepared_effect_joint_writes'])
        assert removed_writes == b['stats']['constructor_prefix_operations']
        assert (a['stage_spine']['stats']['effect_slots_initialized']
                == b['stage_spine']['stats']['effect_slots_initialized'] + after['prefix_result_initializations'])
        old_growths = before['prefix_witness_growths'] + a['stage_spine']['stats']['effect_buffer_growths']
        new_growths = after['prefix_witness_growths'] + b['stage_spine']['stats']['effect_buffer_growths']
        assert b['stage_spine']['owned_output_storage']['pooled_buffers'] == a['stage_spine']['owned_output_storage']['pooled_buffers']
        assert b['stage_spine']['owned_output_storage']['pooled_capacity_bytes'] <= a['stage_spine']['owned_output_storage']['pooled_capacity_bytes']
        delta = read(root / f'{case}-work.json')
        result['workloads'][case] = {
            'program_sha256': b['program_sha256'], 'state_sha256': state, 'runs': len(b['steps']),
            'exact_final_state_and_ordered_run_summaries': True,
            'logical_graph_query_repair_and_boundary_work_unchanged': True,
            'removed_source_receipt_writes': a['stats']['constructor_prefix_receipt_writes'],
            'removed_intermediate_result_writes': removed_writes,
            'combined_result_buffer_growths': [old_growths, new_growths],
            'constructor_preparation_before': before, 'constructor_preparation_after': after,
            'spine_work_changes': spine_differences,
            'owned_output_storage': [a['stage_spine']['owned_output_storage'], b['stage_spine']['owned_output_storage']],
            'instance_header_bytes': b['query_workers']['instance_header_bytes'],
            'execution_header_bytes': b['cell_execution']['rhs_owner_bytes'],
            'compiled_payload_bytes': [a['cell_execution']['compiled_payload_bytes'], b['cell_execution']['compiled_payload_bytes']],
            'effect_plan_slot_bytes': [a['stage_spine']['effect_plan_slot_bytes'], b['stage_spine']['effect_plan_slot_bytes']],
            'effect_plan_layout_bytes': b['stage_spine']['effect_plan_layout_bytes'],
            'effect_plan_support_bytes': {k: [a['stage_spine'][k], b['stage_spine'][k]] for k in (
                'joint_result_plan_bytes', 'effect_plan_registration_bytes', 'effect_plan_cache_bytes')},
            'net_saved_uncalibrated_operations': delta['net_saved_operations'],
            'work_ledger_sha256': sha(root / f'{case}-work.json'),
        }
    acceptance = read(root / 'semantic-acceptance.json')
    assert acceptance['status'] == 'pass'
    assert acceptance['input_sha256']['cpu_values'] == result['workloads']['sum']['state_sha256']
    result['native_sum_acceptance'] = {'status': 'pass', 'sha256': sha(root / 'semantic-acceptance.json')}
    output.write_text(json.dumps(result, indent=2) + '\n')
    print('same state, Runs, queries and effects; result transfer costs recorded')


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    check(*map(Path, sys.argv[1:]))
