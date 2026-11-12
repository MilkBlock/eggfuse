#!/usr/bin/env python3
"""Check source-ordered construction across statically independent scalar writes."""
import hashlib
import json
from pathlib import Path
import sys


def read(path):
    return json.loads(path.read_text())


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def work(value):
    if not isinstance(value, dict):
        return value
    return {k: sum(v) if isinstance(v, list) and 'worker_' in k else work(v)
            for k, v in value.items() if not k.endswith(('_seconds', '_ns'))}


def check(root, prior, output):
    result = {'scope': 'standalone Cell CPU; work and semantics, not a timing campaign',
              'control_commit': '877ff5d2', 'runtime_sha256': sha(root / 'runtime'),
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
        for key in ('stats', 'maintenance', 'free_join', 'entry_schedule', 'known_results',
                    'neighbor_context', 'indexed_columns', 'repair_ports', 'multi_stage',
                    'cell_ownership', 'live_cells', 'fact_decode_calls', 'fact_decode_ports',
                    'stage_spine', 'query_workers'):
            assert work(a[key]) == work(b[key]), (case, key)
        before, after = [r['cell_execution']['runtime']['stats'] for r in (a, b)]
        for key, value in before.items():
            if key not in ('boundaries', 'births'):
                assert value == after[key], (case, key)
        assert before['boundaries'][1:] == after['boundaries'][1:]
        old, new = before['births'], after['births']
        assert new['committed_rows'] == new['local_births']
        assert new['committed_reuses'] == new['local_reuses']
        assert new['discarded_rows'] == new['invalidated'] == 0
        assert new['worker_operations'] == new['committed_rows'] + new['committed_reuses']
        saved_queries = new['worker_operations'] - old['worker_operations']
        assert a['key_lookup_calls'] - b['key_lookup_calls'] == saved_queries
        plan = b['cell_execution']['local_construction']
        assert plan['schema'] == 'cell-local-births/v2'
        assert plan['independent_scheduling'] is False
        assert a['cell_execution']['rhs_owner_bytes'] == b['cell_execution']['rhs_owner_bytes']
        assert a['query_workers']['instance_header_bytes'] == b['query_workers']['instance_header_bytes']
        delta = read(root / f'{case}-work.json')
        result['workloads'][case] = {
            'program_sha256': b['program_sha256'], 'state_sha256': state, 'runs': len(b['steps']),
            'exact_final_state_and_ordered_run_summaries': True,
            'graph_effects_queries_repair_and_publication_work_unchanged': True,
            'total_lookup_calls': [a['key_lookup_calls'], b['key_lookup_calls']],
            'source_constructor_boundaries': [before['boundaries'][0], after['boundaries'][0]],
            'local_construction_before': old, 'local_construction_after': new,
            'compiled_local_plan_before': a['cell_execution']['local_construction'],
            'compiled_local_plan_after': plan,
            'useful_constructors_per_worker_batch': [c['worker_operations'] / c['worker_batches'] for c in (old, new)],
            'instance_header_bytes': b['query_workers']['instance_header_bytes'],
            'execution_header_bytes': b['cell_execution']['rhs_owner_bytes'],
            'compiled_execution_bytes': [a['cell_execution']['compiled_payload_bytes'], b['cell_execution']['compiled_payload_bytes']],
            'net_saved_uncalibrated_operations': delta['net_saved_operations'],
            'work_ledger_sha256': sha(root / f'{case}-work.json'),
        }
    acceptance = read(root / 'semantic-acceptance.json')
    assert acceptance['status'] == 'pass'
    assert acceptance['input_sha256']['cpu_values'] == result['workloads']['sum']['state_sha256']
    result['native_sum_acceptance'] = {'status': 'pass', 'sha256': sha(root / 'semantic-acceptance.json')}
    output.write_text(json.dumps(result, indent=2) + '\n')
    print('same states, Run summaries and effects; scalar-write continuation work accounted')


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    check(*map(Path, sys.argv[1:]))
