#!/usr/bin/env python3
"""Verify owned RHS admission work and saved semantic evidence, without timing."""
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
    births = execution['births']
    return {
        'scheduler': {k: v for k, v in execution['scheduler'].items() if not k.endswith('_ns')},
        'key_lookup_calls': report['key_lookup_calls'],
        'births': {k: births[k] for k in ('worker_operations', 'committed_rows', 'shared_bytes',
            'shared_slots', 'duplicate_evaluations', 'unit_candidates', 'unit_inserts', 'unit_invalidated',
            'slot_leases', 'slot_reattachments', 'root_snapshots', 'root_writes', 'root_merges')},
    }


def collect(control, candidate):
    keys = runpy.run_path(str(Path(__file__).parents[1] / 'raytrace-parallel/measure.py'))['KEYS']
    effects = ('constructor_requests', 'constructor_reused', 'logical_facts_created',
               'function_updates', 'union_requests', 'unions', 'bindings')
    result = {
        'scope': 'actual standalone Cell CPU; work counts, not native runtime performance',
        'control_commit': 'f5bd0c91', 'control_runtime_sha256': sha(control / 'candidate-runtime'),
        'candidate_runtime_sha256': sha(candidate / 'candidate-runtime'),
        'new_performance_measurement': False,
        'overlap_measurement': 'unfinished-producer-after-instance-start/v1',
        'capacity_accounting': 'cumulative payload capacity, not peak live memory or total allocations',
        'workloads': {},
    }
    for case in ('sum', 'ray'):
        a, b = (read(root / f'candidate-{case}/report.json') for root in (control, candidate))
        assert a['status'] == b['status'] == 'complete'
        assert a['program_sha256'] == b['program_sha256']
        state = sha(candidate / f'candidate-{case}/state.json')
        assert state == sha(control / f'candidate-{case}/state.json')
        runs = [[s[k] for k in keys] for s in a['steps']]
        assert runs == [[s[k] for k in keys] for s in b['steps']]
        assert all(a['stats'][k] == b['stats'][k] for k in effects)
        old, new = work(a), work(b)
        q = new['scheduler']
        assert q.get('admission_overlap_instances', 0) <= q['instances']
        assert q.get('admission_jobs', 0) <= q['jobs']
        assert q['max_ready'] <= 64
        assert new['births']['unit_candidates'] == new['births']['unit_inserts'] + new['births']['unit_invalidated']
        result['workloads'][case] = {
            'program_sha256': b['program_sha256'], 'state_sha256': state, 'runs': len(runs),
            'exact_final_state_and_run_summaries': True, 'logical_effects_equal': True,
            'work': {'control': old, 'candidate': new},
            'extra_key_lookups': new['key_lookup_calls'] - old['key_lookup_calls'],
        }
        # Keep both intermediate execution records. Neither was a timing
        # comparison; the last one also predates the earlier-repair gate.
        intermediate = {}
        for prefix in ('initial', 'before-parent-fence'):
            path = candidate / f'{prefix}-candidate-{case}'
            assert sha(path / 'state.json') == state
            intermediate[prefix] = work(read(path / 'report.json'))
        result['workloads'][case]['intermediate_work_only'] = intermediate
    ray = result['workloads']['ray']['work']['candidate']['scheduler']
    assert ray['admission_waves'] > 0 and ray['admission_jobs'] > 0
    assert ray['admission_overlap_instances'] > 0
    assert ray['admission_dependency_waits'] > 0
    proof = read(candidate / 'semantic-acceptance.json')
    assert proof['status'] == 'pass'
    assert proof['input_sha256']['cpu_values'] == result['workloads']['sum']['state_sha256']
    result['native_sum_semantic_acceptance'] = {'status': 'pass', 'sha256': sha(candidate / 'semantic-acceptance.json')}
    return result


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    result = collect(Path(sys.argv[1]), Path(sys.argv[2]))
    Path(sys.argv[3]).write_text(json.dumps(result, indent=2) + '\n')
    print('Owned admission coverage, exact states, ordered Run summaries and sum semantic acceptance verified')
