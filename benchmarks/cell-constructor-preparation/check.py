#!/usr/bin/env python3
"""Check source lookup takeover and semantic regression using saved executions."""
import hashlib
import json
from pathlib import Path
import sys


def read(p):
    return json.loads(p.read_text())


def sha(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def check(root, prior, output):
    result = {'scope': 'standalone Cell CPU; work and semantic evidence, not timing',
              'control_commit': '38c39c56', 'runtime_sha256': sha(root / 'runtime'),
              'control_runtime_sha256': sha(prior / 'runtime'), 'workloads': {}}
    step_keys = ('ordinal', 'ruleset', 'path', 'iterations', 'epoch',
                 'logical_matches', 'executed_bindings', 'changed')
    new = ('constructor_prepared_inputs', 'constructor_prepared_checks',
           'constructor_prepared_fields', 'constructor_prepared_accepted', 'constructor_prepared_rejected')
    for case in ('sum', 'ray'):
        a, b = [read(base / case / 'report.json') for base in (prior, root)]
        assert a['status'] == b['status'] == 'complete'
        assert a['program_sha256'] == b['program_sha256']
        state = sha(root / case / 'state.json')
        assert state == sha(prior / case / 'state.json')
        assert [[s[k] for k in step_keys] for s in a['steps']] == [[s[k] for k in step_keys] for s in b['steps']]
        assert set(b['stats']) - set(a['stats']) == set(new)
        for key, value in a['stats'].items():
            assert value == b['stats'][key], (case, 'stats', key)
        for key in ('maintenance', 'free_join', 'entry_schedule', 'known_results', 'neighbor_context',
                    'indexed_columns', 'repair_ports', 'multi_stage', 'cell_ownership', 'stable_ports', 'live_cells'):
            assert a[key] == b[key], (case, key)
        for key, value in a['stage_spine']['stats'].items():
            if not key.endswith('_seconds'):
                assert value == b['stage_spine']['stats'][key], (case, 'stage_spine', key)
        prep = b['query_workers']['stats']['execution']['constructor']
        costs = {key: b['stats'][key] for key in new}
        accepted = costs['constructor_prepared_accepted']
        checks = costs['constructor_prepared_checks']
        source_inputs = costs['constructor_prepared_inputs']
        assert checks == accepted + costs['constructor_prepared_rejected']
        assert prep['hits'] >= source_inputs >= checks
        assert prep['lookups'] >= prep['hits'] + prep['misses']
        assert b['key_lookup_calls'] - a['key_lookup_calls'] == prep['lookups'] - accepted
        workers = sum(b['query_workers']['stats']['worker_constructor_lookups'])
        assert 0 < workers <= prep['lookups']
        delta = read(root / f'{case}-work.json')
        result['workloads'][case] = {
            'program_sha256': b['program_sha256'], 'state_sha256': state, 'runs': len(b['steps']),
            'exact_final_state_ordered_run_summaries_and_prior_graph_work': True,
            'preparation': prep, 'source': costs, 'worker_lookups': workers,
            'unused_before_source': prep['hits'] - source_inputs,
            'unused_at_source': source_inputs - checks,
            'total_key_lookups': [a['key_lookup_calls'], b['key_lookup_calls']],
            'source_key_lookups_removed': accepted,
            'fact_decode_calls': [a['fact_decode_calls'], b['fact_decode_calls']],
            'instance_header_bytes': [a['query_workers']['instance_header_bytes'], b['query_workers']['instance_header_bytes']],
            'execution_header_bytes': [a['cell_execution']['rhs_owner_bytes'], b['cell_execution']['rhs_owner_bytes']],
            'compiled_payload_bytes': [a['cell_execution']['compiled_payload_bytes'], b['cell_execution']['compiled_payload_bytes']],
            'matched_preparation': b['query_workers']['matched'],
            'plan': b['cell_execution']['constructor_preparation'],
            'net_saved_uncalibrated_operations': delta['net_saved_operations'],
            'work_ledger_sha256': sha(root / f'{case}-work.json'),
        }
    acceptance = read(root / 'semantic-acceptance.json')
    assert acceptance['status'] == 'pass'
    assert acceptance['input_sha256']['cpu_values'] == result['workloads']['sum']['state_sha256']
    result['native_sum_acceptance'] = {'status': 'pass', 'sha256': sha(root / 'semantic-acceptance.json')}
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    check(*map(Path, sys.argv[1:]))
