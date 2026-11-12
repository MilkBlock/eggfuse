#!/usr/bin/env python3
"""Check table-owner work and saved semantic evidence; no timing comparison."""
import hashlib
import json
from pathlib import Path
import runpy
import sys


def read(path):
    return json.loads(path.read_text())


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def work(report):
    execution = report['cell_execution']['runtime']['stats']
    return {
        'registry': {k: v for k, v in report['stats'].items() if k.startswith('unit_registry_')},
        'key_lookup_calls': report['key_lookup_calls'],
        'scheduler': {k: v for k, v in execution['scheduler'].items() if not k.endswith('_ns')},
        'births': {k: execution['births'][k] for k in (
            'worker_operations', 'committed_rows', 'shared_bytes', 'shared_slots',
            'duplicate_evaluations', 'unit_candidates', 'unit_inserts', 'unit_invalidated',
            'slot_leases', 'slot_reattachments', 'root_snapshots', 'root_writes', 'root_merges')},
    }


def collect(control, candidate):
    keys = runpy.run_path(str(Path(__file__).parents[1] / 'raytrace-parallel/measure.py'))['KEYS']
    effects = ('constructor_requests', 'constructor_reused', 'logical_facts_created',
               'function_updates', 'union_requests', 'unions', 'bindings')
    result = {
        'scope': 'actual standalone Cell CPU; work counts, not native runtime performance',
        'control_commit': 'b913ab20',
        'control_runtime_sha256': sha(control / 'candidate-runtime'),
        'candidate_runtime_sha256': sha(candidate / 'candidate-runtime'),
        'new_performance_measurement': False,
        'capacity_accounting': 'cumulative payload capacity, not peak memory or total allocation bytes',
        'workloads': {},
    }
    for case in ('sum', 'ray'):
        a, b = (read(root / f'candidate-{case}/report.json') for root in (control, candidate))
        assert a['status'] == b['status'] == 'complete'
        assert a['program_sha256'] == b['program_sha256']
        state = sha(candidate / f'candidate-{case}/state.json')
        assert state == sha(control / f'candidate-{case}/state.json')
        runs = [[step[k] for k in keys] for step in a['steps']]
        assert runs == [[step[k] for k in keys] for step in b['steps']]
        assert all(a['stats'][k] == b['stats'][k] for k in effects)
        old, new = work(a), work(b)
        counts = new['registry']
        assert counts['unit_registry_pool_calls'] == counts['unit_registry_batches']
        assert counts['unit_registry_worker_identity_rows'] == counts['unit_registry_identity_rows'] == counts['unit_registry_candidates']
        assert counts['unit_registry_discarded'] == 0
        assert counts['unit_registry_installs'] <= counts['unit_registry_candidates']
        births = new['births']
        assert births['unit_candidates'] == births['unit_inserts'] + births['unit_invalidated']
        assert all(old['births'][k] == births[k] for k in ('unit_candidates', 'unit_inserts', 'unit_invalidated'))
        assert new['scheduler']['max_ready'] <= 64
        result['workloads'][case] = {
            'program_sha256': b['program_sha256'], 'state_sha256': state, 'runs': len(runs),
            'exact_final_state_and_run_summaries': True, 'logical_effects_equal': True,
            'work': {'control': old, 'candidate': new},
            'extra_key_lookups': new['key_lookup_calls'] - old['key_lookup_calls'],
            'extra_registry_capacity_bytes': counts['unit_registry_bytes'] - old['registry']['unit_registry_bytes'],
        }
    assert result['workloads']['ray']['work']['candidate']['registry']['unit_registry_worker_identity_rows'] > 0
    proof = read(candidate / 'semantic-acceptance.json')
    assert proof['status'] == 'pass'
    assert proof['input_sha256']['cpu_values'] == result['workloads']['sum']['state_sha256']
    result['native_sum_semantic_acceptance'] = {
        'status': 'pass', 'sha256': sha(candidate / 'semantic-acceptance.json'),
    }
    return result


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    result = collect(Path(sys.argv[1]), Path(sys.argv[2]))
    Path(sys.argv[3]).write_text(json.dumps(result, indent=2) + '\n')
    print('Worker table ownership, exact states, ordered Run summaries and sum acceptance verified')
