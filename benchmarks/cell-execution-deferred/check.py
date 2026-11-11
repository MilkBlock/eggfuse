#!/usr/bin/env python3
"""Check deferred Cell ownership against saved source-Run executions."""
import json
from pathlib import Path
import runpy
import sys


def check(root, prior, output):
    helpers = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'cell-execution-matched/check.py'))
    read, sha = helpers['read'], helpers['sha']
    result = {
        'scope': 'standalone Cell CPU', 'control_commit': '1a6de877',
        'runtime_sha256': sha(root / 'runtime'), 'control_runtime_sha256': sha(prior / 'runtime'),
        'limits': 'Complete work and semantic checks, not throughput or utilization evidence. '
                  'Cursor ownership stays on the coordinator; shared effects remain ordered. '
                  'Deferred preparation is a subset of matched and total preparation. '
                  'Header size alone is not total storage; capacity excludes allocator overhead.',
        'workloads': {},
    }
    step_keys = ('ordinal', 'ruleset', 'path', 'iterations', 'epoch',
                 'logical_matches', 'executed_bindings', 'changed')
    consumed_keys = ('prepared_rhs_operations', 'prepared_rhs_later_operations')
    for case in ('sum', 'ray'):
        a, b = [read(base / case / 'report.json') for base in (prior, root)]
        assert a['status'] == b['status'] == 'complete'
        assert a['program_sha256'] == b['program_sha256']
        state = sha(root / case / 'state.json')
        assert sha(prior / case / 'state.json') == state
        assert [[s[k] for k in step_keys] for s in a['steps']] == [[s[k] for k in step_keys] for s in b['steps']]
        for key in ('key_lookup_calls', 'maintenance', 'free_join', 'entry_schedule',
                    'known_results', 'neighbor_context', 'indexed_columns', 'repair_ports'):
            assert a[key] == b[key], (case, key)
        for key, value in a['stats'].items():
            if key not in consumed_keys:
                assert b['stats'][key] == value, (case, key, value, b['stats'][key])
        old, new = a['query_workers']['stats'], b['query_workers']['stats']
        for key in ('entries', 'answers', 'point_reads', 'key_operations', 'constructors',
                    'answer_buffer_allocations', 'completion_headers', 'completion_binding_moves'):
            assert old[key] == new[key], (case, 'query', key)
        for key in ('serial_order_headers', 'deferred_winner_moves'):
            assert old[key] > 0 and new[key] == 0
        before, after = [r['cell_execution']['runtime']['stats'] for r in (a, b)]
        matched = b['query_workers']['matched']
        added = new['execution']['operations'] - old['execution']['operations']
        consumed = sum(b['stats'][k] - a['stats'][k] for k in consumed_keys)
        assert added == matched['deferred_operations'] > 0
        assert 0 < consumed <= added
        assert after['worker_segments'] < before['worker_segments']
        assert after['failures'] == before['failures'] == 0
        assert a['cell_execution']['compiled_payload_bytes'] == b['cell_execution']['compiled_payload_bytes']
        storage = b['stage_spine']['query_candidate_storage']
        assert storage['pending_groups'] == storage['pending_cursor_slots'] == 0
        ss = b['stage_spine']['stats']
        result['workloads'][case] = {
            'runs': len(b['steps']), 'program_sha256': b['program_sha256'], 'state_sha256': state,
            'before_report_sha256': sha(prior / case / 'report.json'),
            'after_report_sha256': sha(root / case / 'report.json'),
            'same_final_state_ordered_run_summaries_and_checked_graph_query_maintenance_work': True,
            'prepared_added': added, 'consumed_added': consumed, 'added_not_consumed': added - consumed,
            'total_prepared_not_consumed': new['execution']['operations'] - sum(b['stats'][k] for k in consumed_keys),
            'preparation_before': old['execution'], 'preparation_after': new['execution'],
            'consumption_before_after': {k: [a['stats'][k], b['stats'][k]] for k in consumed_keys},
            'matched_before': a['query_workers']['matched'], 'matched_after': matched,
            'resumption_before': before, 'resumption_after': after,
            'removed_handoffs': {k: [old[k], new[k]] for k in ('serial_order_headers', 'deferred_winner_moves', 'batch_buffers')},
            'winner_bytes_before_after': [a['stage_spine']['query_winner_bytes'], b['stage_spine']['query_winner_bytes']],
            'candidate_storage': storage,
            'candidate_work': {k: ss[k] for k in ('candidate_cursor_stores', 'candidate_cursor_growths',
                'candidate_cursor_peak_bytes', 'losing_cursor_releases', 'aborted_cursor_releases',
                'deferred_group_growths', 'deferred_group_peak_bytes')},
            'fragment_storage_before_after': {k: [a['stage_spine']['stats'][k], ss[k]] for k in
                ('query_fragment_slots', 'query_fragment_capacity_bytes', 'query_fragment_sealed_slots',
                 'query_fragment_sealed_capacity_bytes')},
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
