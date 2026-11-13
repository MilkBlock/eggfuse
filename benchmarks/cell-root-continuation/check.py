#!/usr/bin/env python3
"""Keep semantics exact while charging root admission work."""
import hashlib
import json
from pathlib import Path
import runpy
import sys

prior = runpy.run_path(str(Path(__file__).parents[1] / 'cell-run-queue/check.py'))
read, sha = prior['read'], prior['sha']


def work(report):
    result = prior['work'](report)
    result['maintenance'] = report['maintenance']
    source = report['cell_execution']['runtime']['stats']['births']
    for k in ('root_existing_reuses', 'root_existing_key_fields', 'root_collision_misses'):
        result['births'][k] = source.get(k, 0)
    return result


def collect(control, candidate, *, control_commit='552db678', required_extra=()):
    keys = runpy.run_path(str(Path(__file__).parents[1] / 'raytrace-parallel/measure.py'))['KEYS']
    effects = ('constructor_requests', 'constructor_reused', 'logical_facts_created',
               'function_updates', 'union_requests', 'unions', 'bindings')
    validation = read(candidate / 'validation.json') + read(candidate / 'readme-checks.json')
    required = {'runtime', 'integration-query_workers', 'integration-cell_execution',
                'integration-cell_owner_pipeline', 'collisions', 'collision-registration',
                'all-features', 'sparse', 'legacy', 'storage-root-trace',
                'readme-compile', 'readme-run', 'readme-bench', 'release-build'}
    required.update(required_extra)
    assert required <= {c['name'] for c in validation}
    assert all(c['exit_code'] == 0 for c in validation)
    manifest = read(candidate / 'manifest.json')
    assert manifest['runtime_sha256'] == sha(candidate / 'candidate-runtime')
    assert manifest['control_commit'] == control_commit
    result = {
        'scope': 'actual standalone Cell CPU; work/semantics, no speed claim or native Raytrace proof',
        'control_commit': control_commit,
        'control_runtime_sha256': sha(control / 'candidate-runtime'),
        'candidate_runtime_sha256': manifest['runtime_sha256'],
        'validation': validation, 'workloads': {},
    }
    for case in ('sum', 'ray'):
        config = manifest['lanes'][case]
        original = read(control / 'manifest.json')['lanes'][case]
        assert config['exit_code'] == 0
        assert config['args'] == original['args'] and config['program'] == original['program']
        a, b = (read(root / f'candidate-{case}/report.json') for root in (control, candidate))
        assert a['status'] == b['status'] == 'complete'
        assert a['program_sha256'] == b['program_sha256']
        state = sha(candidate / f'candidate-{case}/state.json')
        assert state == sha(control / f'candidate-{case}/state.json'), (case, 'final state')
        runs = [[s[k] for k in keys] for s in a['steps']]
        assert runs == [[s[k] for k in keys] for s in b['steps']], (case, 'Run summaries')
        assert all(a['stats'][k] == b['stats'][k] for k in effects), (case, 'logical effects')
        assert a['maintenance']['reverse_headers'] == b['maintenance']['reverse_headers']
        assert a['maintenance']['stats']['live_reverse_edges'] == b['maintenance']['stats']['live_reverse_edges']
        # The sparse forward directory was intentionally removed; reverse
        # incidence and observable semantics retain their exact requirements.
        assert b['maintenance']['dependency_headers'] == 0
        previous_evidence = a['stage_spine']['iterative_bake']
        current_evidence = b['stage_spine']['iterative_bake']
        assert all(current_evidence[k] == v for k, v in previous_evidence.items())
        added_evidence = {k: v for k, v in current_evidence.items() if k not in previous_evidence}
        assert added_evidence == {}
        old, new = work(a), work(b)
        births = new['births']
        assert births['root_jobs'] == births['root_births'] + births['root_reuses']
        assert births['slot_leases'] == births['slot_reattachments']
        assert births['committed_rows'] == births['local_births']
        assert births['root_existing_reuses'] > 0
        assert births['root_existing_key_fields'] > 0
        assert births['root_bucket_fallbacks'] == births['root_existing_reuses'] + births['root_collision_misses']
        registry = new['registration']
        assert registry['constructor_registry_rows'] == registry['constructor_registry_adopted']
        assert registry['constructor_registry_discarded'] == registry['unit_registry_discarded'] == 0
        assert new['fused']['constructor_fused_rows'] > 0
        assert new['fused']['constructor_fused_staging_bytes'] == 0
        assert new['scheduler']['rule_group_carries'] > 0
        assert new['scheduler']['mixed_rule_batches'] > 0
        result['workloads'][case] = {
            'program_sha256': b['program_sha256'], 'state_sha256': state,
            'runs': len(runs), 'exact_final_state_run_summaries_and_effects': True,
            'schedule_sha256': hashlib.sha256(json.dumps(runs, separators=(',', ':')).encode()).hexdigest(),
            'logical_effects': {k: b['stats'][k] for k in effects},
            'existing_iterative_evidence_unchanged': True,
            'added_iterative_counters': added_evidence,
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
    print('Root continuation: exact source Runs/final states/effects and native sum acceptance passed')
