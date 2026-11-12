#!/usr/bin/env python3
"""Check grouped execution and slimmer events against unchanged source effects."""
import hashlib
import json
from pathlib import Path
import runpy
import sys

prior = runpy.run_path(str(Path(__file__).parents[1] / 'cell-root-births/check.py'))
read, sha = prior['read'], prior['sha']


def work(report):
    result = prior['work'](report)
    stats = report['cell_execution']['runtime']['stats']
    for key in ('execution_groups', 'evaluations', 'duplicate_evaluations', 'hashes',
                'unit_worker_rows', 'unit_bytes', 'frame_handles', 'result_handles',
                'slot_growths', 'shared_growths', 'pending_growths', 'value_writes'):
        result['births'][key] = stats['births'].get(key, 0)
    for key in ('event_completed_early', 'event_early_cells'):
        result['scheduler'][key] = stats['scheduler'][key]
    return result


def collect(control, candidate):
    keys = runpy.run_path(str(Path(__file__).parents[1] / 'raytrace-parallel/measure.py'))['KEYS']
    effects = ('constructor_requests', 'constructor_reused', 'logical_facts_created',
               'function_updates', 'union_requests', 'unions', 'bindings')
    validation = read(candidate / 'validation.json') + read(candidate / 'readme-checks.json')
    assert all(check['exit_code'] == 0 for check in validation)
    manifest = read(candidate / 'manifest.json')
    assert manifest['runtime_sha256'] == sha(candidate / 'candidate-runtime')
    result = {'scope': 'actual standalone Cell CPU work; no timing claim or native Raytrace proof',
              'control_commit': 'c0dd0034', 'control_runtime_sha256': sha(control / 'candidate-runtime'),
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
        assert roots['root_births'] > 0
        assert 0 < roots['execution_groups'] < new['scheduler']['jobs']
        assert new['scheduler']['event_bytes'] < old['scheduler']['event_bytes']
        assert b['stats']['constructor_registry_discarded'] == b['stats']['unit_registry_discarded'] == 0
        result['workloads'][case] = {
            'program_sha256': b['program_sha256'], 'state_sha256': state, 'runs': len(runs),
            'schedule_sha256': hashlib.sha256(json.dumps(runs, separators=(',', ':')).encode()).hexdigest(),
            'exact_final_state_run_summaries_and_effects': True,
            'logical_effects': {k: b['stats'][k] for k in effects},
            'work': {'control': old, 'candidate': new},
            'fixed_layout_bytes': {k: b['cell_execution']['local_construction'][k]
                for k in ('completed_cell_bytes', 'worker_statistics_bytes')},
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
    print('Grouped Cell execution, exact source Runs and native sum contract verified')
