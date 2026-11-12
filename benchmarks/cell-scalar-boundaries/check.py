#!/usr/bin/env python3
"""Account for constructor continuation across already completed scalar slots."""
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
    result = {'scope': 'standalone Cell CPU; work and semantics, not timing',
              'control_commit': '14d1bcc2', 'runtime_sha256': sha(root / 'runtime'),
              'control_runtime_sha256': sha(prior / 'runtime'), 'workloads': {}}
    fields = ('ordinal', 'ruleset', 'path', 'iterations', 'epoch',
              'logical_matches', 'executed_bindings', 'changed')
    for case in ('sum', 'ray'):
        a, b = [read(base / case / 'report.json') for base in (prior, root)]
        assert a['status'] == b['status'] == 'complete'
        assert a['program_sha256'] == b['program_sha256']
        state = sha(root / case / 'state.json')
        assert state == sha(prior / case / 'state.json')
        assert [[s[k] for k in fields] for s in a['steps']] == [[s[k] for k in fields] for s in b['steps']]
        for key, value in a['stats'].items():
            if not key.startswith(('constructor_prefix_', 'constructor_prepared_')):
                assert value == b['stats'][key], (case, key, value, b['stats'][key])
        assert b['stats']['constructor_prefix_rejected'] == 0
        for key in ('maintenance', 'free_join', 'entry_schedule', 'known_results',
                    'neighbor_context', 'indexed_columns', 'repair_ports', 'multi_stage',
                    'cell_ownership', 'live_cells', 'fact_decode_calls'):
            assert a[key] == b[key], (case, key)
        old_run, new_run = [r['cell_execution']['runtime']['stats'] for r in (a, b)]
        for key, value in old_run.items():
            if key != 'boundaries':
                assert value == new_run[key], (case, key)
        assert old_run['boundaries'][1:] == new_run['boundaries'][1:]
        removed_boundaries = old_run['boundaries'][0] - new_run['boundaries'][0]
        assert removed_boundaries > 0
        before, after = [r['query_workers']['stats']['execution']['constructor'] for r in (a, b)]
        assert before['attempts'] == after['attempts']
        assert after['prefix_scalar_checks'] > 0
        assert after['prefix_scalar_stops'] == 0
        old_source = a['key_lookup_calls'] - before['lookups']
        new_source = b['key_lookup_calls'] - after['lookups']
        assert old_source - new_source == after['hits'] - before['hits'] > 0
        assert b['key_lookup_calls'] - a['key_lookup_calls'] == after['misses'] - before['misses']
        for key in ('instance_bytes', 'inline_evidence_bytes'):
            assert a['cell_execution']['constructor_preparation'][key] == b['cell_execution']['constructor_preparation'][key]
        assert a['cell_execution']['rhs_owner_bytes'] == b['cell_execution']['rhs_owner_bytes']
        assert b['stage_spine']['owned_output_storage']['pooled_buffers'] <= a['stage_spine']['owned_output_storage']['pooled_buffers']
        assert b['stage_spine']['owned_output_storage']['pooled_capacity_bytes'] <= a['stage_spine']['owned_output_storage']['pooled_capacity_bytes']
        spine = {k: [a['stage_spine']['stats'].get(k), v] for k, v in b['stage_spine']['stats'].items()
                 if not k.endswith('_seconds') and a['stage_spine']['stats'].get(k) != v}
        delta = read(root / f'{case}-work.json')
        result['workloads'][case] = {
            'program_sha256': b['program_sha256'], 'state_sha256': state, 'runs': len(b['steps']),
            'exact_final_state_and_ordered_run_summaries': True,
            'logical_effects_lhs_queries_repair_and_scalar_consumption_unchanged': True,
            'removed_source_constructor_boundaries': removed_boundaries,
            'source_lookup_calls': [old_source, new_source],
            'total_lookup_calls': [a['key_lookup_calls'], b['key_lookup_calls']],
            'constructor_preparation_before': before, 'constructor_preparation_after': after,
            'constructor_prefix_operations': [a['stats']['constructor_prefix_operations'], b['stats']['constructor_prefix_operations']],
            'spine_work_changes': spine,
            'owned_output_storage': [a['stage_spine']['owned_output_storage'], b['stage_spine']['owned_output_storage']],
            'instance_header_bytes': b['query_workers']['instance_header_bytes'],
            'execution_header_bytes': b['cell_execution']['rhs_owner_bytes'],
            'compiled_payload_bytes': [a['cell_execution']['compiled_payload_bytes'], b['cell_execution']['compiled_payload_bytes']],
            'effect_plan_support_bytes': {k: [a['stage_spine'][k], b['stage_spine'][k]] for k in (
                'effect_plan_slot_bytes', 'effect_plan_layout_bytes', 'joint_result_plan_bytes',
                'effect_plan_registration_bytes', 'effect_plan_cache_bytes')},
            'net_saved_uncalibrated_operations': delta['net_saved_operations'],
            'work_ledger_sha256': sha(root / f'{case}-work.json'),
        }
    acceptance = read(root / 'semantic-acceptance.json')
    assert acceptance['status'] == 'pass'
    assert acceptance['input_sha256']['cpu_values'] == result['workloads']['sum']['state_sha256']
    result['native_sum_acceptance'] = {'status': 'pass', 'sha256': sha(root / 'semantic-acceptance.json')}
    output.write_text(json.dumps(result, indent=2) + '\n')
    print('same effects, final states and ordered Runs; continuation work and costs accounted')


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    check(*map(Path, sys.argv[1:]))
