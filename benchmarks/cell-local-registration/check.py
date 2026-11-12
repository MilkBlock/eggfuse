#!/usr/bin/env python3
"""Check per-Cell frame return against the preceding actual Cell runtime."""
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
              'control_commit': 'd62f83d1', 'control_runtime_sha256': sha(control / 'candidate-runtime'),
              'candidate_runtime_sha256': sha(candidate / 'candidate-runtime'), 'workloads': {},
              'validation': read(candidate / 'validation.json') + read(candidate / 'readme-checks.json')}
    assert all(check['exit_code'] == 0 for check in result['validation'])
    assert result['candidate_runtime_sha256'] == read(candidate / 'manifest.json')['runtime_sha256']
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
        am, bm = (r['maintenance']['stats'] for r in (a, b))
        omitted = 'subscription_root_reads_omitted'
        assert am.keys() == bm.keys()
        assert all(am[k] == bm[k] for k in am if k != omitted), (case, 'maintenance')
        assert bm[omitted] >= am[omitted]
        assert a['maintenance']['reverse_headers'] == b['maintenance']['reverse_headers']
        assert a['maintenance']['dependency_headers'] == b['maintenance']['dependency_headers']
        assert a['sieve']['stats'] == b['sieve']['stats']
        assert a['stage_spine']['iterative_bake'] == b['stage_spine']['iterative_bake']
        old, new = (r['cell_execution']['runtime']['stats']['births'] for r in (a, b))
        for k in ('local_births', 'local_reuses', 'committed_rows', 'unit_candidates',
                  'unit_inserts', 'unit_invalidated', 'slot_leases', 'slot_reattachments'):
            assert old[k] == new[k], (case, k)
        s = b['stats']
        assert s['unit_registry_discarded'] == 0
        assert s['unit_registry_reserved_slots'] == s['unit_registry_candidates']
        assert s['unit_registry_identity_rows'] == s['unit_registry_candidates']
        assert s['unit_registry_worker_identity_rows'] == s['unit_registry_candidates']
        assert s['unit_registry_pool_calls'] == s['unit_registry_batches']
        assert s['unit_registry_field_handles'] == s['unit_registry_candidates']
        assert s['unit_registry_reserved_slots'] == (s['unit_registry_installs'] +
                   s['unit_registry_trimmed_slots'] + s['unit_registry_retained_holes'])
        assert s['constructor_registry_adopted'] == s['constructor_registry_rows']
        assert s['constructor_registry_discarded'] == 0
        assert s['unit_registry_deferred_subscriptions'] == s['unit_registry_worker_subscriptions']
        assert s['unit_registry_worker_subscriptions'] <= s['unit_registry_installs']
        assert s['constructor_registry_pre_return_cells'] <= s['constructor_registry_frame_transfers']
        assert s['constructor_registry_frame_transfers'] <= s['unit_registry_accepted_cells']
        if case == 'ray':
            assert s['unit_registry_retained_holes'] > 0
            assert s['unit_registry_worker_subscriptions'] > 0
            assert s['constructor_registry_pre_return_cells'] > 0
            assert bm[omitted] > am[omitted]
            assert 0 < s['unit_registry_early_cells'] <= s['unit_registry_accepted_cells']
            assert s['unit_registry_decision_fragments'] > s['unit_registry_batches']
        else:
            assert s['unit_registry_field_handles'] == s['unit_registry_event_bytes'] == 0

        def work(r):
            s = r['stats']
            return {k: s.get(k, 0) for k in ('unit_registry_batches', 'unit_registry_candidates',
                'unit_registry_installs', 'unit_registry_bytes', 'unit_registry_pool_calls',
                'unit_registry_reserved_slots', 'unit_registry_reserved_bytes',
                'unit_registry_capacity_growth_bytes', 'unit_registry_retained_holes',
                'unit_registry_trimmed_slots', 'constructor_registry_adopted',
                'constructor_registry_bytes', 'unit_registry_field_handles',
                'unit_registry_decision_fragments', 'unit_registry_decision_bytes',
                'unit_registry_event_bytes', 'unit_registry_event_wait_ns',
                'unit_registry_ready_prefixes', 'unit_registry_early_cells', 'unit_registry_accepted_cells',
                'unit_registry_deferred_subscriptions', 'unit_registry_worker_subscriptions',
                'unit_registry_subscription_tasks', 'unit_registry_subscription_queue_bytes',
                'constructor_registry_frame_bytes', 'constructor_registry_frame_events',
                'constructor_registry_frame_transfers', 'constructor_registry_pre_return_cells')}
        slot_bytes = (s['unit_registry_reserved_bytes'] // s['unit_registry_reserved_slots']
                      if s['unit_registry_reserved_slots'] else None)
        result['workloads'][case] = {
            'program_sha256': b['program_sha256'], 'state_sha256': state, 'runs': len(runs),
            'schedule_sha256': hashlib.sha256(json.dumps(runs, separators=(',', ':')).encode()).hexdigest(),
            'exact_final_state_runs_effects_and_reverse_edges': True,
            'additional_subscription_root_reads_omitted': bm[omitted] - am[omitted],
            'logical_effects': {k: s[k] for k in effects},
            'work': {'control': work(a), 'candidate': work(b)},
            'function_and_decoded_slot_bytes': slot_bytes,
            'retained_invalid_slot_payload_bytes': s['unit_registry_retained_holes'] * (slot_bytes or 0),
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
    print('Per-Cell frame return, exact source Runs and native sum contract verified')
