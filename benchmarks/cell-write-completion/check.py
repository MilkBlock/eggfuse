#!/usr/bin/env python3
"""Check event-driven write retirement against saved current-branch execution."""
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
        'writes': {k: v for k, v in execution['writes'].items() if not k.endswith('_ns')},
        'maintenance': report['maintenance'],
        'key_lookup_calls': report['key_lookup_calls'],
        'scheduler': {k: v for k, v in execution['scheduler'].items() if not k.endswith('_ns')},
    }


def collect(control, candidate):
    keys = runpy.run_path(str(Path(__file__).parents[1] / 'raytrace-parallel/measure.py'))['KEYS']
    effects = ('constructor_requests', 'constructor_reused', 'logical_facts_created',
               'function_updates', 'union_requests', 'unions', 'bindings')
    result = {
        'scope': 'actual standalone Cell CPU; work counts, not native runtime performance',
        'control_commit': 'c27cbcf1',
        'control_runtime_sha256': sha(control / 'candidate-runtime'),
        'candidate_runtime_sha256': sha(candidate / 'candidate-runtime'),
        'capacity_accounting': 'cumulative payload capacity, not peak memory or total allocator traffic',
        'overlap_measurement': 'unfinished-write-blocks-after-retirement/v1',
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
        counts = new['writes']
        assert all(counts[k] == value for k, value in old['writes'].items() if k != 'temporary_bytes')
        assert counts['owner_retired_rows'] == counts['rows']
        assert counts['owner_completion_early_groups'] <= counts['owner_completion_groups']
        assert counts['owner_pool_calls'] == counts['batches']
        assert new['key_lookup_calls'] == old['key_lookup_calls']
        ma, mb = old['maintenance']['stats'], new['maintenance']['stats']
        shifts = {'subscription_value_visits': -1, 'canonical_subscription_calls': 1,
                  'subscription_scalar_fields_skipped': 1, 'subscription_root_reads_omitted': 1}
        for key, value in ma.items():
            assert mb[key] == value + shifts.get(key, 0) * counts['new_rows'], key
        assert new['maintenance']['reverse_headers'] == old['maintenance']['reverse_headers']
        assert new['maintenance']['dependency_headers'] == old['maintenance']['dependency_headers']
        result['workloads'][case] = {
            'program_sha256': b['program_sha256'], 'state_sha256': state, 'runs': len(runs),
            'schedule_sha256': hashlib.sha256(json.dumps(runs, separators=(',', ':')).encode()).hexdigest(),
            'exact_final_state_and_run_summaries': True, 'logical_effects_equal': True,
            'work': {'control': old, 'candidate': new},
            'payload_capacity_change_bytes': counts['temporary_bytes'] - old['writes']['temporary_bytes'],
        }
    assert result['workloads']['ray']['work']['candidate']['writes']['owner_completion_early_groups'] > 0
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
    print('Worker retirement, exact states, ordered Run summaries and sum acceptance verified')
