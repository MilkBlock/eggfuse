#!/usr/bin/env python3
"""Check that a Cell's existing result handoff removes redundant preparation."""
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
              'control_commit': '0368e471', 'runtime_sha256': sha(root / 'runtime'),
              'control_runtime_sha256': sha(prior / 'runtime'),
              'admission_counter_payload_bytes': 7 * 8, 'workloads': {}}
    new = ('preparation_handoff_rule_checks', 'preparation_handoff_history_checks',
           'preparation_handoff_checks', 'preparation_handoff_operations',
           'preparation_handoff_reads', 'preparation_handoff_inherited_reads', 'preparation_handoff_skips')
    steps = ('ordinal', 'ruleset', 'path', 'iterations', 'epoch',
             'logical_matches', 'executed_bindings', 'changed')
    for case in ('sum', 'ray'):
        a, b = [read(base / case / 'report.json') for base in (prior, root)]
        assert a['status'] == b['status'] == 'complete'
        assert a['program_sha256'] == b['program_sha256']
        state = sha(root / case / 'state.json')
        assert state == sha(prior / case / 'state.json')
        assert [[s[k] for k in steps] for s in a['steps']] == [[s[k] for k in steps] for s in b['steps']]
        assert a['stats'].keys() == b['stats'].keys()
        for key, value in a['stats'].items():
            if not key.startswith('constructor_prepared_'):
                assert value == b['stats'][key], (case, key, value, b['stats'][key])
        old, new_spine = a['stage_spine']['stats'], b['stage_spine']['stats']
        assert set(new_spine) - set(old) == set(new)
        for key, value in old.items():
            if not key.endswith('_seconds'):
                assert value == new_spine[key], (case, 'stage_spine', key)
        for key in ('maintenance', 'free_join', 'entry_schedule', 'known_results',
                    'neighbor_context', 'indexed_columns', 'repair_ports', 'multi_stage',
                    'cell_ownership', 'live_cells'):
            assert a[key] == b[key], (case, key)
        before = a['query_workers']['stats']['execution']['constructor']
        after = b['query_workers']['stats']['execution']['constructor']
        removed = before['lookups'] - after['lookups']
        lost_accepts = a['stats']['constructor_prepared_accepted'] - b['stats']['constructor_prepared_accepted']
        assert removed > 0
        assert a['key_lookup_calls'] - b['key_lookup_calls'] == removed - lost_accepts
        # Suppression is applied at candidate formation, before winner selection;
        # a losing candidate is not credited as a removed executed probe.
        assert new_spine['preparation_handoff_skips'] >= removed
        assert after['lookups'] == after['hits'] + after['misses']
        for parent, key in [('query_workers', 'instance_header_bytes'),
                            ('cell_execution', 'rhs_owner_bytes')]:
            assert a[parent][key] == b[parent][key], (case, parent, key)
        delta = read(root / f'{case}-work.json')
        result['workloads'][case] = {
            'program_sha256': b['program_sha256'], 'state_sha256': state, 'runs': len(b['steps']),
            'exact_final_state_and_ordered_run_summaries': True,
            'original_graph_and_handoff_work_unchanged': True,
            'admission_work': {key: new_spine[key] for key in new},
            'constructor_preparation_before': before, 'constructor_preparation_after': after,
            'removed_probes': removed,
            'source_witness_acceptances': [a['stats']['constructor_prepared_accepted'], b['stats']['constructor_prepared_accepted']],
            'total_key_lookups': [a['key_lookup_calls'], b['key_lookup_calls']],
            'matched_preparation_before': a['query_workers']['matched'],
            'matched_preparation_after': b['query_workers']['matched'],
            'instance_header_bytes': b['query_workers']['instance_header_bytes'],
            'execution_header_bytes': b['cell_execution']['rhs_owner_bytes'],
            'compiled_payload_bytes': [a['cell_execution']['compiled_payload_bytes'], b['cell_execution']['compiled_payload_bytes']],
            'preparation_rules': b['cell_execution']['constructor_preparation']['rules'],
            'handoff_rules': b['cell_execution']['constructor_preparation']['handoff_rules'],
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
