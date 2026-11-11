#!/usr/bin/env python3
"""Check owned-match preparation using saved complete runtime executions."""
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
    result = {
        'scope': 'standalone Cell CPU', 'control_commit': '35a59e30',
        'runtime_sha256': sha(root / 'runtime'),
        'control_runtime_sha256': sha(prior / 'runtime'),
        'limits': 'Complete work and semantic checks, not throughput or utilization evidence. '
                  'Source shared effects remain ordered. New matched preparation is a subset '
                  'of total preparation, not additional savings. Capacity bytes are cumulative '
                  'and exclude allocator overhead; they are not peak memory.',
        'workloads': {},
    }
    step_keys = ('ordinal', 'ruleset', 'path', 'iterations', 'epoch',
                 'logical_matches', 'executed_bindings', 'changed')
    preparation_keys = ('prepared_rhs_operations', 'prepared_rhs_later_operations')
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
            if key not in preparation_keys:
                assert b['stats'][key] == value, (case, 'stats', key, value, b['stats'][key])
        old, new = a['query_workers']['stats'], b['query_workers']['stats']
        for key in ('entries', 'answers', 'point_reads', 'key_operations', 'constructors',
                    'answer_buffer_allocations', 'completion_headers', 'completion_binding_moves'):
            assert old[key] == new[key], (case, 'query', key)
        before, after = [r['cell_execution']['runtime']['stats'] for r in (a, b)]
        assert b['cell_execution']['runtime']['grain'] == 1
        matched = b['query_workers']['matched']
        prepared_added = new['execution']['operations'] - old['execution']['operations']
        consumed_added = sum(b['stats'][k] - a['stats'][k] for k in preparation_keys)
        assert prepared_added == matched['execution']['operations'] > 0
        assert matched['worker_operations'] + matched['inline_operations'] == prepared_added
        assert consumed_added == prepared_added
        assert a['cell_execution']['compiled_payload_bytes'] == b['cell_execution']['compiled_payload_bytes']
        assert after['worker_segments'] < before['worker_segments']
        assert after['failures'] == before['failures'] == 0
        assert matched['execution']['deferred_failures'] == matched['execution']['later_deferred_failures'] == 0
        prepared = new['execution']['operations']
        consumed = sum(b['stats'][k] for k in preparation_keys)
        assert 0 <= consumed <= prepared
        result['workloads'][case] = {
            'runs': len(b['steps']), 'program_sha256': b['program_sha256'], 'state_sha256': state,
            'before_report_sha256': sha(prior / case / 'report.json'),
            'after_report_sha256': sha(root / case / 'report.json'),
            'same_state_ordered_run_summaries_and_checked_graph_query_maintenance_work': True,
            'preparation_before': old['execution'], 'preparation_after': new['execution'],
            'consumed_before': {k: a['stats'][k] for k in preparation_keys},
            'consumed_after': {k: b['stats'][k] for k in preparation_keys},
            'prepared_added': prepared_added, 'consumed_added': consumed_added,
            'consumed_added_outside_resumption_counter': consumed_added - (before['local_operations'] - after['local_operations']),
            'total_prepared_not_consumed': prepared - consumed,
            'matched': matched, 'instance_header_bytes': b['query_workers']['instance_header_bytes'],
            'resumption_before': before, 'resumption_after': after,
            'worker_preparation_before': old['worker_local_operations'],
            'worker_preparation_after': new['worker_local_operations'],
            'compiled_plan_bytes': b['cell_execution']['compiled_payload_bytes'],
            'query_batch_buffers_before_after': [old['batch_buffers'], new['batch_buffers']],
            'spine_fragment_storage': {k: [a['stage_spine']['stats'][k], b['stage_spine']['stats'][k]]
                for k in ('query_fragment_slots', 'query_fragment_capacity_bytes',
                          'query_fragment_sealed_slots', 'query_fragment_sealed_capacity_bytes')},
        }
    accepted = read(root / 'semantic-acceptance.json')
    assert accepted['status'] == 'pass'
    assert accepted['input_sha256']['cpu_values'] == result['workloads']['sum']['state_sha256']
    result['native_sum_acceptance'] = {'status': 'pass', 'sha256': sha(root / 'semantic-acceptance.json')}
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({case: {k: v[k] for k in ('prepared_added', 'consumed_added',
        'total_prepared_not_consumed', 'matched', 'resumption_after')} for case, v in result['workloads'].items()}, indent=2))


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    check(*map(Path, sys.argv[1:]))
