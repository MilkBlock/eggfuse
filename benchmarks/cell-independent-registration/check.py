#!/usr/bin/env python3
"""Check independent constructor ownership without weakening source semantics."""
import hashlib
import json
from pathlib import Path
import runpy
import sys

prior = runpy.run_path(str(Path(__file__).parents[1] / 'cell-worker-runs/check.py'))
read, sha = prior['read'], prior['sha']


def work(report):
    result = prior['work'](report)
    result['registration'] = {k: v for k, v in report['stats'].items() if '_registry_' in k and not k.endswith('_ns')}
    result['source_installs_of_local_rows'] = result['births']['local_births'] - report['stats']['constructor_registry_adopted']
    return result


def collect(control, candidate):
    keys = runpy.run_path(str(Path(__file__).parents[1] / 'raytrace-parallel/measure.py'))['KEYS']
    effects = ('constructor_requests', 'constructor_reused', 'logical_facts_created',
               'function_updates', 'union_requests', 'unions', 'bindings')
    validation = read(candidate / 'validation.json') + read(candidate / 'readme-checks.json')
    assert all(check['exit_code'] == 0 for check in validation)
    manifest = read(candidate / 'manifest.json')
    assert manifest['runtime_sha256'] == sha(candidate / 'candidate-runtime')
    assert manifest['control_commit'] == '68fb07a4'
    result = {'scope': 'actual standalone Cell CPU work; no timing claim or native Raytrace proof',
              'control_commit': '68fb07a4', 'control_runtime_sha256': sha(control / 'candidate-runtime'),
              'candidate_runtime_sha256': manifest['runtime_sha256'], 'validation': validation, 'workloads': {}}
    for case in ('sum', 'ray'):
        config = manifest['lanes'][case]
        assert config['exit_code'] == 0
        original = read(control / 'manifest.json')['lanes'][case]
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
        assert a['maintenance']['dependency_headers'] == b['maintenance']['dependency_headers']
        assert a['stage_spine']['iterative_bake'] == b['stage_spine']['iterative_bake']
        old, new = work(a), work(b)
        roots = new['births']
        assert roots['root_jobs'] == roots['root_births'] + roots['root_reuses']
        assert roots['slot_leases'] == roots['slot_reattachments']
        assert roots['committed_rows'] == roots['local_births']
        registry = new['registration']
        assert registry['constructor_registry_rows'] == registry['constructor_registry_adopted']
        assert registry['constructor_registry_independent_rows'] > 0
        assert registry['constructor_registry_functionless_batches'] > 0
        assert new['source_installs_of_local_rows'] < old['source_installs_of_local_rows']
        assert registry['constructor_registry_discarded'] == registry['unit_registry_discarded'] == 0
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
    print('Independent constructor ownership, exact source Runs and native sum contract verified')
