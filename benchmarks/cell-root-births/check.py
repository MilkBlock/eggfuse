#!/usr/bin/env python3
"""Compare actual root completion with the preceding frozen Cell runtime."""
import gzip
import hashlib
import json
from pathlib import Path
import runpy
import sys


def read(path):
    return json.loads(path.read_text())


def sha(path):
    stream = path.open('rb') if path.exists() else gzip.open(str(path) + '.gz', 'rb')
    with stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def work(report):
    stats = report['cell_execution']['runtime']['stats']
    births = stats['births']
    return {
        'key_lookup_calls': report['key_lookup_calls'],
        'frames': stats['frames'], 'source_boundaries': stats['boundaries'],
        'births': {k: births.get(k, 0) for k in (
            'root_bucket_probes', 'root_bucket_fallbacks', 'root_pending', 'root_boundary_probes',
            'root_isolated', 'root_hash_bytes', 'directory_checks',
            'root_jobs', 'root_births', 'root_reuses', 'local_births', 'local_reuses',
            'worker_operations', 'committed_rows', 'source_operand_reads', 'operand_reads',
            'candidate_probes', 'field_checks', 'shared_slots', 'shared_bytes', 'slot_leases',
            'slot_reattachments', 'slot_bytes', 'sealed_bytes', 'unit_candidates', 'unit_inserts',
            'unit_invalidated', 'pending_bytes')},
        'scheduler': {k: stats['scheduler'][k] for k in (
            'jobs', 'batches', 'queue_bytes', 'event_bytes', 'admission_waves',
            'effect_flushes', 'dependency_flushes')},
        'registration': {k: report['stats'][k] for k in (
            'constructor_registry_rows', 'constructor_registry_bytes', 'constructor_registry_frame_bytes',
            'unit_registry_bytes', 'unit_registry_event_bytes', 'unit_registry_subscription_queue_bytes')},
    }


def collect(control, candidate):
    keys = runpy.run_path(str(Path(__file__).parents[1] / 'raytrace-parallel/measure.py'))['KEYS']
    effects = ('constructor_requests', 'constructor_reused', 'logical_facts_created',
               'function_updates', 'union_requests', 'unions', 'bindings')
    validation = read(candidate / 'validation.json') + read(candidate / 'readme-checks.json')
    assert all(check['exit_code'] == 0 for check in validation)
    manifest = read(candidate / 'manifest.json')
    assert manifest['runtime_sha256'] == sha(candidate / 'candidate-runtime')
    result = {'scope': 'actual standalone Cell CPU work; no timing claim or native Raytrace proof',
              'control_commit': '916ebf7c', 'control_runtime_sha256': sha(control / 'candidate-runtime'),
              'candidate_runtime_sha256': manifest['runtime_sha256'], 'validation': validation, 'workloads': {}}
    for case in ('sum', 'ray'):
        assert manifest['lanes'][case]['exit_code'] == 0
        a, b = (read(root / f'candidate-{case}/report.json') for root in (control, candidate))
        assert a['status'] == b['status'] == 'complete'
        assert a['program_sha256'] == b['program_sha256']
        state = sha(candidate / f'candidate-{case}/state.json')
        assert state == sha(control / f'candidate-{case}/state.json'), (case, 'final state')
        runs = [[s[k] for k in keys] for s in a['steps']]
        assert runs == [[s[k] for k in keys] for s in b['steps']], (case, 'Run summaries')
        assert all(a['stats'][k] == b['stats'][k] for k in effects), (case, 'logical effects')
        assert a['maintenance']['reverse_headers'] == b['maintenance']['reverse_headers']
        assert a['maintenance']['dependency_headers'] == b['maintenance']['dependency_headers']
        assert a['stage_spine']['iterative_bake'] == b['stage_spine']['iterative_bake']
        old, new = work(a), work(b)
        roots = new['births']
        assert roots['root_jobs'] == roots['root_births'] + roots['root_reuses']
        assert roots['slot_leases'] == roots['slot_reattachments']
        assert roots['committed_rows'] == roots['local_births']
        assert roots['root_births'] > 0
        assert b['key_lookup_calls'] < a['key_lookup_calls']
        assert b['stats']['constructor_registry_discarded'] == b['stats']['unit_registry_discarded'] == 0
        result['workloads'][case] = {
            'program_sha256': b['program_sha256'], 'state_sha256': state, 'runs': len(runs),
            'schedule_sha256': hashlib.sha256(json.dumps(runs, separators=(',', ':')).encode()).hexdigest(),
            'exact_final_state_run_summaries_and_effects': True,
            'logical_effects': {k: b['stats'][k] for k in effects},
            'work': {'control': old, 'candidate': new},
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
    print('Actual root completion, source Runs and native sum contract verified')
