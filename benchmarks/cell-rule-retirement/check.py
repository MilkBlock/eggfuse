#!/usr/bin/env python3
"""Check rule-owner retirement work against saved completion-event executions.

This is a work/semantic check, not a performance harness. Native acceptance
remains the separate, unchanged sum-bits choice_diagnosis.py entrypoint.
"""
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


def collect(control, candidate):
    keys = runpy.run_path(str(Path(__file__).parents[1] / 'raytrace-parallel/measure.py'))['KEYS']
    effects = ('constructor_requests', 'constructor_reused', 'logical_facts_created',
               'function_updates', 'union_requests', 'unions', 'bindings')
    result = {
        'scope': 'actual standalone Cell CPU; work counts, not native runtime timing',
        'control_commit': 'b8fbf090', 'control_runtime_commit': '2ae7b97e',
        'control_runtime_sha256': sha(control / 'candidate-runtime'),
        'candidate_runtime_sha256': sha(candidate / 'candidate-runtime'),
        'new_performance_measurement': False, 'workloads': {},
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
        assert a['key_lookup_calls'] == b['key_lookup_calls']
        # A different Cursor/slot policy must not masquerade as moving the
        # existing merge. Both lifetimes and sealed instance payloads agree.
        cursor_keys = ('candidate_cursor_stores', 'losing_cursor_releases',
                       'query_fragment_sealed_slots', 'query_fragment_sealed_capacity_bytes')
        assert all(a['stage_spine']['stats'][k] == b['stage_spine']['stats'][k] for k in cursor_keys)
        measures = {k: v for k, v in b['query_workers']['stats'].items() if k.startswith('final_merge_')}
        total = measures['final_merge_worker_rows'] + measures['final_merge_inline_rows']
        result['workloads'][case] = {
            'program_sha256': b['program_sha256'], 'state_sha256': state,
            'exact_final_state_and_run_summaries': True, 'runs': len(runs),
            'logical_effects_equal': True, 'key_lookup_calls': b['key_lookup_calls'],
            'final_merge': measures,
            'worker_fraction_of_final_merge_rows': measures['final_merge_worker_rows'] / total if total else 0,
            'cursor_and_slot_counts': {k: b['stage_spine']['stats'][k] for k in cursor_keys},
        }
    assert result['workloads']['ray']['final_merge']['final_merge_worker_rows'] > 0
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
    print('Exact states, ordered Run summaries, logical effects, original owners and sum acceptance verified')
