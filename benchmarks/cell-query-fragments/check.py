#!/usr/bin/env python3
"""Check frozen final states, Run/effect order and result transport accounting."""
import hashlib
import json
from pathlib import Path
import runpy
import sys


def check(root):
    common = runpy.run_path(str(Path(__file__).parents[1] / 'cell-bake-full-merge/check.py'))
    read, sha = common['read'], common['sha']
    keys = runpy.run_path(str(Path(__file__).parents[1] / 'raytrace-parallel/measure.py'))['KEYS']
    effects = ('constructor_requests', 'constructor_reused', 'logical_facts_created',
               'function_updates', 'union_requests', 'unions', 'bindings', 'merge_calls')
    validation = read(root / 'checks/validation.json')
    assert {v['name'] for v in validation} == {'runtime-unit', 'integration', 'legacy',
        'all-features', 'readme-compile', 'readme-run', 'readme-bench', 'release'}
    assert all(v['exit_code'] == 0 for v in validation)
    paths = [root / lane for lane in ('control', 'candidate')]
    manifests = [read(p / 'manifest.json') for p in paths]
    assert all(sha(p / 'candidate-runtime') == m['runtime_sha256'] for p,m in zip(paths,manifests))
    result = dict(scope='actual standalone Cell CPU; native sum contract and differential Raytrace',
                  control_commit=manifests[1]['control_commit'], validation=validation, workloads={})
    for case in ('sum', 'ray'):
        configs = [m['lanes'][case] for m in manifests]
        assert all(c['exit_code'] == 0 for c in configs)
        assert all(configs[0][k] == configs[1][k] for k in ('program', 'args'))
        reports = [read(p / f'candidate-{case}/report.json') for p in paths]
        old, new = reports
        assert old['status'] == new['status'] == 'complete'
        assert old['program_sha256'] == new['program_sha256']
        state = sha(paths[1] / f'candidate-{case}/state.json')
        assert state == sha(paths[0] / f'candidate-{case}/state.json'), (case, 'state')
        runs = [[s[k] for k in keys] for s in old['steps']]
        assert runs == [[s[k] for k in keys] for s in new['steps']], (case, 'Run summaries')
        assert all(old['stats'][k] == new['stats'][k] for k in effects), (case, 'effects')
        assert old['stage_spine']['iterative_bake'] == new['stage_spine']['iterative_bake']
        work = {}
        for label, report in zip(('control', 'candidate'), reports):
            q = report['query_workers']['stats']
            residual = report['query_workers']['residual_expansion']
            work[label] = dict(query={k:v for k,v in q.items() if k.startswith('result_')},
                               residual=residual)
        q = work['candidate']['query']
        w = work['candidate']['residual']['stats']
        assert q['result_fragment_rows'] == w['fragment_gather_rows']
        assert w['fragment_worker_rows'] + w['fragment_inline_rows'] == w['fragment_gather_rows']
        assert w['fragment_inline_rows'] == 0, 'only already large worker finishes qualify'
        assert q['result_fragment_rows'] + q['result_coordinator_rows'] == w['answers']
        assert work['control']['residual']['stats']['answers'] == w['answers']
        result['workloads'][case] = dict(state_sha256=state, source_runs=len(runs),
            exact_state_runs_effects_bake_evidence=True, work=work,
            schedule_sha256=hashlib.sha256(json.dumps(runs,separators=(',', ':')).encode()).hexdigest())
    proof = read(paths[1] / 'semantic-acceptance.json')
    assert proof['status'] == 'pass'
    assert proof['input_sha256']['cpu_values'] == result['workloads']['sum']['state_sha256']
    result['native_sum_acceptance'] = dict(status='pass', sha256=sha(paths[1] / 'semantic-acceptance.json'))
    return result


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    Path(sys.argv[2]).write_text(json.dumps(check(Path(sys.argv[1])), indent=2) + '\n')
    print('Exact state, source Runs, effects, Bake evidence and native sum acceptance pass')
