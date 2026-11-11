#!/usr/bin/env python3
"""Check certificate-based source continuation using saved full executions."""
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
              'control_commit': 'bde30d99', 'runtime_sha256': sha(root / 'runtime'),
              'control_runtime_sha256': sha(prior / 'runtime'), 'workloads': {}}
    new = ('constructor_prepared_certificates', 'constructor_prepared_liveness_checks',
           'constructor_prepared_result_reads', 'constructor_prepared_sealed',
           'constructor_prepared_key_fields_avoided')
    steps = ('ordinal', 'ruleset', 'path', 'iterations', 'epoch',
             'logical_matches', 'executed_bindings', 'changed')
    for case in ('sum', 'ray'):
        a, b = [read(base / case / 'report.json') for base in (prior, root)]
        assert a['status'] == b['status'] == 'complete'
        assert a['program_sha256'] == b['program_sha256']
        state = sha(root / case / 'state.json')
        assert state == sha(prior / case / 'state.json')
        assert [[s[k] for k in steps] for s in a['steps']] == [[s[k] for k in steps] for s in b['steps']]
        assert set(b['stats']) - set(a['stats']) == set(new)
        for key, value in a['stats'].items():
            if key != 'constructor_prepared_fields':
                assert value == b['stats'][key], (case, key, value, b['stats'][key])
        for key in ('key_lookup_calls', 'maintenance', 'free_join', 'entry_schedule',
                    'known_results', 'neighbor_context', 'indexed_columns', 'repair_ports',
                    'multi_stage', 'cell_ownership', 'live_cells'):
            assert a[key] == b[key], (case, key)
        for key, value in a['stage_spine']['stats'].items():
            if not key.endswith('_seconds'):
                assert value == b['stage_spine']['stats'][key], (case, 'stage_spine', key)
        prep = b['query_workers']['stats']['execution']['constructor']
        assert prep == a['query_workers']['stats']['execution']['constructor']
        costs = {key: b['stats'][key] for key in new}
        assert costs['constructor_prepared_certificates'] == b['stats']['constructor_prepared_checks']
        assert costs['constructor_prepared_certificates'] >= costs['constructor_prepared_liveness_checks']
        assert costs['constructor_prepared_liveness_checks'] >= costs['constructor_prepared_sealed'] > 0
        assert costs['constructor_prepared_result_reads'] == costs['constructor_prepared_sealed']
        assert a['stats']['constructor_prepared_fields'] - b['stats']['constructor_prepared_fields'] == costs['constructor_prepared_key_fields_avoided']
        for parent, key in [('query_workers', 'instance_header_bytes'),
                            ('cell_execution', 'rhs_owner_bytes'), ('cell_execution', 'compiled_payload_bytes')]:
            assert a[parent][key] == b[parent][key], (case, parent, key)
        delta = read(root / f'{case}-work.json')
        result['workloads'][case] = {
            'program_sha256': b['program_sha256'], 'state_sha256': state, 'runs': len(b['steps']),
            'exact_final_state_and_ordered_run_summaries': True,
            'unchanged_prior_graph_work_except_validation_fields': True,
            'certificate_work': costs,
            'validation_fields': [a['stats']['constructor_prepared_fields'], b['stats']['constructor_prepared_fields']],
            'speculative_lookups': prep['lookups'], 'total_key_lookups': b['key_lookup_calls'],
            'source_witnesses_accepted': b['stats']['constructor_prepared_accepted'],
            'source_witnesses_rejected': b['stats']['constructor_prepared_rejected'],
            'fact_decodes': [a['fact_decode_calls'], b['fact_decode_calls']],
            'decoded_fields': [a['fact_decode_ports'], b['fact_decode_ports']],
            'instance_header_bytes': b['query_workers']['instance_header_bytes'],
            'execution_header_bytes': b['cell_execution']['rhs_owner_bytes'],
            'compiled_payload_bytes': b['cell_execution']['compiled_payload_bytes'],
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
