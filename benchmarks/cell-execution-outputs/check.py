#!/usr/bin/env python3
"""Check independently owned Cell publication results against saved executions."""
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
    result = {'scope': 'standalone Cell CPU, not native egglog', 'control_commit': '3ace9e35',
              'runtime_sha256': sha(root / 'runtime'), 'control_runtime_sha256': sha(prior / 'runtime'),
              'limits': 'Result ownership and work comparison; no throughput claim. Ordinary history '
                        'capture, active_rhs and ownership Entry contexts remain. Capacity excludes '
                        'allocator overhead; growth counters are not a complete allocation profile.',
              'workloads': {}}
    step_keys = ('ordinal', 'ruleset', 'path', 'iterations', 'epoch',
                 'logical_matches', 'executed_bindings', 'changed')
    storage_changes = {'joint_scratch_growths', 'joint_scratch_growth_bytes',
                       'shared_output_arena_borrows', 'peak_cell_output_slots'}
    new_costs = ('owned_effect_frames', 'effect_buffer_takes', 'effect_buffer_returns', 'effect_buffer_reuses', 'effect_buffer_growths',
                 'effect_buffer_growth_bytes', 'effect_buffer_pool_growths',
                 'effect_buffer_pool_growth_bytes', 'publication_buffer_moves')
    for case in ('sum', 'ray'):
        a, b = [read(base / case / 'report.json') for base in (prior, root)]
        assert a['status'] == b['status'] == 'complete'
        assert a['program_sha256'] == b['program_sha256']
        state = sha(root / case / 'state.json')
        assert sha(prior / case / 'state.json') == state
        assert [[s[k] for k in step_keys] for s in a['steps']] == [[s[k] for k in step_keys] for s in b['steps']]
        for key in ('stats', 'key_lookup_calls', 'maintenance', 'free_join', 'entry_schedule',
                    'known_results', 'neighbor_context', 'indexed_columns', 'repair_ports', 'multi_stage'):
            assert a[key] == b[key], (case, key)
        for key, value in a['stage_spine']['stats'].items():
            if not key.endswith('_seconds') and key not in storage_changes:
                assert value == b['stage_spine']['stats'][key], (case, 'stage', key, value, b['stage_spine']['stats'][key])
        for key, value in a['query_workers']['stats'].items():
            after = b['query_workers']['stats'][key]
            if key in ('worker_entries', 'worker_local_operations', 'worker_steps'):
                assert len(value) == len(after) and sum(value) == sum(after), (case, key)
            elif not key.endswith('_seconds'):
                assert value == after, (case, 'query', key)
        assert a['query_workers']['matched'] == b['query_workers']['matched']
        assert a['cell_execution']['runtime']['stats'] == b['cell_execution']['runtime']['stats']
        assert a['cell_execution']['compiled_payload_bytes'] == b['cell_execution']['compiled_payload_bytes']
        stats = b['stage_spine']['stats']
        assert stats['shared_output_arena_borrows'] == 0
        assert stats['owned_effect_frames'] == stats['effect_frames']
        assert stats['publication_buffer_moves'] > 0
        assert stats['cell_output_receipts'] == stats['cell_output_deliveries']
        storage = b['stage_spine']['owned_output_storage']
        assert storage['pending_capacity_bytes'] == 0
        result['workloads'][case] = {
            'runs': len(b['steps']), 'program_sha256': b['program_sha256'], 'state_sha256': state,
            'before_report_sha256': sha(prior / case / 'report.json'), 'after_report_sha256': sha(root / case / 'report.json'),
            'same_final_state_ordered_run_summaries_and_checked_graph_query_rhs_publication_work': True,
            'shared_arena_borrows_before_after': [a['stage_spine']['stats']['shared_output_arena_borrows'], 0],
            'costs': {key: stats[key] for key in new_costs}, 'storage': storage,
            'completion_header_bytes_before_after': [r['stage_spine']['completion_record_bytes'] for r in (a, b)],
            'execution_header_bytes_before_after': [r['cell_execution']['rhs_owner_bytes'] for r in (a, b)],
            'changed_storage_counters': {key: [r['stage_spine']['stats'][key] for r in (a, b)] for key in sorted(storage_changes)},
            'existing_result_work': {key: stats[key] for key in ('effect_slots_initialized', 'effect_slot_probes',
                'effect_slot_targets', 'history_allocations', 'history_slots_written', 'effect_output_copies', 'cell_output_deliveries')},
        }
    accepted = read(root / 'semantic-acceptance.json')
    assert accepted['status'] == 'pass'
    assert accepted['input_sha256']['cpu_values'] == result['workloads']['sum']['state_sha256']
    result['native_sum_acceptance'] = {'status': 'pass', 'sha256': sha(root / 'semantic-acceptance.json')}
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result['workloads'], indent=2))


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    check(*map(Path, sys.argv[1:]))
