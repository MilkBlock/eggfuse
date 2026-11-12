#!/usr/bin/env python3
"""Check actual constructor ownership, source Runs and the reviewed sum contract."""
import hashlib
import json
from pathlib import Path
import runpy
import sys


def read(path):
    return json.loads(path.read_text())


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def collect(control, candidate):
    keys = runpy.run_path(str(Path(__file__).parents[1] / 'raytrace-parallel/measure.py'))['KEYS']
    effects = ('constructor_requests', 'constructor_reused', 'logical_facts_created',
               'function_updates', 'union_requests', 'unions', 'bindings')
    result = {'scope': 'actual standalone Cell CPU work; not timing or native egglog performance',
              'control_commit': '7b13f259', 'control_runtime_sha256': sha(control / 'candidate-runtime'),
              'candidate_runtime_sha256': sha(candidate / 'candidate-runtime'), 'workloads': {}}
    assert result['candidate_runtime_sha256'] == read(candidate / 'manifest.json')['runtime_sha256']
    for case in ('sum', 'ray'):
        old, new = (read(root / f'candidate-{case}/report.json') for root in (control, candidate))
        assert old['status'] == new['status'] == 'complete'
        assert old['program_sha256'] == new['program_sha256']
        state = sha(candidate / f'candidate-{case}/state.json')
        assert state == sha(control / f'candidate-{case}/state.json')
        runs = [[s[k] for k in keys] for s in old['steps']]
        assert runs == [[s[k] for k in keys] for s in new['steps']]
        assert all(old['stats'][k] == new['stats'][k] for k in effects)
        assert old['key_lookup_calls'] == new['key_lookup_calls']
        assert old['maintenance']['stats'] == new['maintenance']['stats']
        assert old['sieve']['stats'] == new['sieve']['stats']
        assert old['stage_spine']['iterative_bake'] == new['stage_spine']['iterative_bake']
        a, b = (r['cell_execution']['runtime']['stats']['births'] for r in (old, new))
        for k in ('local_births', 'local_reuses', 'committed_rows', 'unit_candidates',
                  'unit_inserts', 'unit_invalidated', 'slot_leases', 'slot_reattachments'):
            assert a[k] == b[k], (case, k)
        s = new['stats']
        assert s['constructor_registry_rows'] == s['constructor_registry_adopted']
        assert s['constructor_registry_rows'] == s['constructor_registry_worker_rows']
        assert s['constructor_registry_discarded'] == 0
        assert s['constructor_registry_fragments'] <= s['constructor_registry_adopted']
        assert s['constructor_registry_batches'] <= s['unit_registry_batches']
        assert s['unit_registry_pool_calls'] == s['unit_registry_batches']
        if case == 'ray':
            assert s['constructor_registry_adopted'] > 0

        def work(report):
            s = report['stats']
            execution = report['cell_execution']['runtime']['stats']
            return {
                'local_constructor_rows': execution['births']['committed_rows'],
                'source_constructor_row_installs': execution['births']['committed_rows'] - s.get('constructor_registry_adopted', 0),
                'worker_constructor_rows': s.get('constructor_registry_worker_rows', 0),
                'constructor_registration_batches': s.get('constructor_registry_batches', 0),
                'constructor_registration_metadata_bytes': s.get('constructor_registry_bytes', 0),
                'source_constructor_table_fragments': s.get('constructor_registry_fragments', 0),
                'unit_registration_pool_calls': s['unit_registry_pool_calls'],
                'unit_registration_candidates': s['unit_registry_candidates'],
                'rhs_completion_event_bytes': execution['scheduler']['event_bytes'],
                'rhs_queue_capacity_bytes': execution['scheduler']['queue_bytes'],
                'global_key_lookups': report['key_lookup_calls'],
            }
        result['workloads'][case] = {
            'program_sha256': new['program_sha256'], 'state_sha256': state, 'runs': len(runs),
            'schedule_sha256': hashlib.sha256(json.dumps(runs, separators=(',', ':')).encode()).hexdigest(),
            'exact_final_state_runs_effects_and_maintenance': True,
            'logical_effects': {k: s[k] for k in effects},
            'work': {'control': work(old), 'candidate': work(new)},
        }
    proof = read(candidate / 'semantic-acceptance.json')
    assert proof['status'] == 'pass'
    assert proof['input_sha256']['cpu_values'] == result['workloads']['sum']['state_sha256']
    result['native_sum_acceptance'] = {'status': 'pass', 'sha256': sha(candidate / 'semantic-acceptance.json')}
    return result


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    Path(sys.argv[3]).write_text(json.dumps(collect(Path(sys.argv[1]), Path(sys.argv[2])), indent=2) + '\n')
    print('Constructor ownership, exact source Runs and native sum contract verified')
