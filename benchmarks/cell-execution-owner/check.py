#!/usr/bin/env python3
"""Check owned source continuations against complete saved Cell executions."""
import json
from pathlib import Path
import runpy
import sys


def check(root, prior, output):
    helpers = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'cell-execution-matched/check.py'))
    read, sha = helpers['read'], helpers['sha']
    result = {
        'scope': 'standalone Cell CPU', 'control_commit': 'c7ad29e9',
        'runtime_sha256': sha(root / 'runtime'), 'control_runtime_sha256': sha(prior / 'runtime'),
        'limits': 'Work and semantic validation, not throughput evidence. The source driver still '
                  'resolves boundaries synchronously; single active_rhs, ordinary output arena and '
                  'current ownership Entry context remain scheduling limits. Owned header bytes '
                  'exclude pointed-to storage and do not measure bytes copied or peak allocation.',
        'workloads': {},
    }
    step_keys = ('ordinal', 'ruleset', 'path', 'iterations', 'epoch',
                 'logical_matches', 'executed_bindings', 'changed')
    new_keys = ('joint_scratch_borrows', 'joint_scratch_growths',
                'joint_scratch_growth_bytes', 'shared_output_arena_borrows')
    for case in ('sum', 'ray'):
        a, b = [read(base / case / 'report.json') for base in (prior, root)]
        assert a['status'] == b['status'] == 'complete'
        assert a['program_sha256'] == b['program_sha256']
        state = sha(root / case / 'state.json')
        assert sha(prior / case / 'state.json') == state
        assert [[s[k] for k in step_keys] for s in a['steps']] == [[s[k] for k in step_keys] for s in b['steps']]
        for key in ('stats', 'key_lookup_calls', 'maintenance', 'free_join', 'entry_schedule',
                    'known_results', 'neighbor_context', 'indexed_columns', 'repair_ports'):
            assert a[key] == b[key], (case, key)
        for key, value in a['stage_spine']['stats'].items():
            if not key.endswith('_seconds'):
                assert value == b['stage_spine']['stats'][key], (case, 'stage', key, value, b['stage_spine']['stats'][key])
        for key, value in a['query_workers']['stats'].items():
            if key in ('worker_entries', 'worker_local_operations', 'worker_steps'):
                # Rayon assignment is nondeterministic; the executed total is
                # authoritative, not which worker happened to own each chunk.
                after = b['query_workers']['stats'][key]
                assert len(value) == len(after) and sum(value) == sum(after), (case, key)
            elif not key.endswith('_seconds'):
                assert value == b['query_workers']['stats'][key], (case, 'query', key)
        assert a['query_workers']['matched'] == b['query_workers']['matched']
        assert a['multi_stage'] == b['multi_stage']
        assert a['cell_execution']['runtime']['stats'] == b['cell_execution']['runtime']['stats']
        assert a['cell_execution']['compiled_payload_bytes'] == b['cell_execution']['compiled_payload_bytes']
        s = b['stage_spine']['stats']
        assert s['joint_scratch_borrows'] == s['joint_history_frames'] > 0
        assert s['shared_output_arena_borrows'] + s['joint_scratch_borrows'] == a['stage_spine']['stats']['effect_frames']
        assert b['cell_execution']['position_owner'] == 'Cell.completed_prefix'
        result['workloads'][case] = {
            'runs': len(b['steps']), 'program_sha256': b['program_sha256'], 'state_sha256': state,
            'before_report_sha256': sha(prior / case / 'report.json'),
            'after_report_sha256': sha(root / case / 'report.json'),
            'same_final_state_ordered_runs_and_checked_graph_query_rhs_publication_work': True,
            'runtime_stats': b['cell_execution']['runtime']['stats'],
            'owned_control_bytes': b['cell_execution']['rhs_owner_bytes'],
            'position_bytes': b['cell_execution']['progress_bytes'],
            'worker_distributions': {k: [a['query_workers']['stats'][k], b['query_workers']['stats'][k]]
                for k in ('worker_entries', 'worker_local_operations', 'worker_steps')},
            'joint_storage': {k: s[k] for k in new_keys},
            'shared_arena_borrows_before_after': [a['stage_spine']['stats']['effect_frames'], s['shared_output_arena_borrows']],
            'existing_result_storage_work': {k: s[k] for k in ('effect_slots_initialized', 'effect_slot_probes',
                'effect_slot_targets', 'history_allocations', 'history_slots_written', 'effect_output_copies',
                'cell_output_deliveries')},
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
