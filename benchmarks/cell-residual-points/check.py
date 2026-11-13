#!/usr/bin/env python3
"""Require unchanged states, source Runs, effects and reviewed native sum proof."""
import hashlib
import json
from pathlib import Path
import runpy
import sys

base = runpy.run_path(str(Path(__file__).parents[1] / 'cell-run-queue/check.py'))
read, sha = base['read'], base['sha']


def collect(control, candidate):
    keys = runpy.run_path(str(Path(__file__).parents[1] / 'raytrace-parallel/measure.py'))['KEYS']
    effects = ('constructor_requests', 'constructor_reused', 'logical_facts_created',
               'function_updates', 'union_requests', 'unions', 'bindings', 'merge_calls')
    checks = read(candidate / 'validation.json') + read(candidate / 'readme-checks.json')
    required = {'integration-parallel_residuals', 'integration-query_workers',
                'integration-cell_execution', 'integration-scoped_completion',
                'integration-entry_publications', 'collision-queries', 'all-features',
                'readme-compile', 'readme-run', 'readme-bench', 'release-build'}
    assert required <= {c['name'] for c in checks} and all(c['exit_code'] == 0 for c in checks)
    manifest = read(candidate / 'manifest.json')
    assert manifest['control_commit'] == 'f0fb1443'
    assert manifest['runtime_sha256'] == sha(candidate / 'candidate-runtime')
    result = {'scope': 'actual standalone Cell CPU; Raytrace is differential, not native proof',
              'control_commit': manifest['control_commit'], 'validation': checks,
              'validation_attempts': read(candidate / 'validation-attempts.json'),
              'control_runtime_sha256': sha(control / 'candidate-runtime'),
              'candidate_runtime_sha256': manifest['runtime_sha256'], 'workloads': {}}
    for case in ('sum', 'ray'):
        a, b = [read(root / f'candidate-{case}/report.json') for root in (control, candidate)]
        old = read(control / 'manifest.json')['lanes'][case]
        new = manifest['lanes'][case]
        assert new['exit_code'] == 0 and all(old[k] == new[k] for k in ('program', 'args'))
        assert a['status'] == b['status'] == 'complete'
        assert a['program_sha256'] == b['program_sha256']
        state = sha(candidate / f'candidate-{case}/state.json')
        assert state == sha(control / f'candidate-{case}/state.json'), (case, 'final state')
        runs = [[s[k] for k in keys] for s in a['steps']]
        assert runs == [[s[k] for k in keys] for s in b['steps']], (case, 'Run summaries')
        assert all(a['stats'][k] == b['stats'][k] for k in effects), (case, 'effects')
        assert a['stage_spine']['iterative_bake'] == b['stage_spine']['iterative_bake']
        for k in ('reverse_headers', 'dependency_headers'):
            assert a['maintenance'][k] == b['maintenance'][k]
        assert a['maintenance']['stats']['live_reverse_edges'] == b['maintenance']['stats']['live_reverse_edges']
        output = {'program_sha256': b['program_sha256'], 'state_sha256': state, 'runs': len(runs),
                  'schedule_sha256': hashlib.sha256(json.dumps(runs, separators=(',', ':')).encode()).hexdigest(),
                  'exact_final_state_run_summaries_effects_iterative_evidence': True, 'work': {}}
        for label, report in (('control', a), ('candidate', b)):
            output['work'][label] = {
                'residual': report['query_workers']['residual_expansion'],
                'query': report['query_workers']['stats'], 'free_join': report['free_join'],
                'source': report['stats'], 'compiled_payload_bytes': report['cell_execution']['compiled_payload_bytes'],
            }
        trial = b['query_workers']['residual_expansion']
        assert trial['compiled_point_entries'] == 177, 'reproduce the trial revision, not the restored default'
        assert (trial['stats']['point_entries'], trial['stats']['point_answers']) == (5, 2)
        result['workloads'][case] = output
    proof = read(candidate / 'semantic-acceptance.json')
    assert proof['status'] == 'pass'
    assert proof['input_sha256']['cpu_values'] == result['workloads']['sum']['state_sha256']
    result['native_sum_acceptance'] = {'status': 'pass', 'sha256': sha(candidate / 'semantic-acceptance.json')}
    return result


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    Path(sys.argv[3]).write_text(json.dumps(collect(Path(sys.argv[1]), Path(sys.argv[2])), indent=2) + '\n')
    print('Exact states, source Runs/effects and native sum acceptance passed')
