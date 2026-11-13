#!/usr/bin/env python3
"""Check the merged runtime against its frozen parallel-branch control."""
import gzip
import hashlib
import json
from pathlib import Path
import runpy
import sys


def read(path):
    return json.loads(path.read_text())


def sha(path):
    opener = path.open if path.exists() else lambda mode: gzip.open(str(path) + '.gz', mode)
    digest = hashlib.sha256()
    with opener('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def check(control, candidate, validation):
    keys = runpy.run_path(str(Path(__file__).parents[1] / 'raytrace-parallel/measure.py'))['KEYS']
    effects = ('constructor_requests', 'constructor_reused', 'logical_facts_created',
               'function_updates', 'union_requests', 'unions', 'bindings', 'merge_calls')
    manifests = [read(root / 'manifest.json') for root in (control, candidate)]
    assert all(sha(root / 'candidate-runtime') == manifest['runtime_sha256']
               for root, manifest in zip((control, candidate), manifests))
    checks = (read(validation / 'validation.json') + read(validation / 'smoke-checks.json')
              + read(validation / 'reconciliation-checks.json'))
    required = {'runtime-unit', 'all-features', 'legacy', 'python-bake', 'examples',
                'readme-compile', 'readme-run', 'readme-bench', 'release-build',
                'post-mainline-ownership', 'post-mainline-examples', 'release-final'}
    required |= {'integration-' + name for name in (
        'cell_ownership', 'parallel_guards', 'completion_batches', 'cell_execution',
        'query_workers', 'parallel_residuals', 'entry_publications', 'scoped_completion',
        'parallel_publication', 'cell_absorption', 'cell_owner_pipeline')}
    assert required <= {c['name'] for c in checks}
    assert all(c['exit_code'] == 0 for c in checks)
    result = {'scope': 'actual standalone Cell CPU; native sum final-state contract and differential Raytrace',
              'control_commit': manifests[1]['control_commit'], 'validation': checks,
              'control_runtime_sha256': manifests[0]['runtime_sha256'],
              'candidate_runtime_sha256': manifests[1]['runtime_sha256'], 'workloads': {}}
    for case in ('sum', 'ray'):
        configs = [m['lanes'][case] for m in manifests]
        assert all(c['exit_code'] == 0 for c in configs)
        assert all(configs[0][k] == configs[1][k] for k in ('program', 'args'))
        old, new = [read(root / f'candidate-{case}/report.json') for root in (control, candidate)]
        assert old['status'] == new['status'] == 'complete'
        assert old['program_sha256'] == new['program_sha256']
        state = sha(candidate / f'candidate-{case}/state.json')
        assert state == sha(control / f'candidate-{case}/state.json'), (case, 'state')
        runs = [[s[k] for k in keys] for s in old['steps']]
        assert runs == [[s[k] for k in keys] for s in new['steps']], (case, 'source Run summaries')
        assert all(old['stats'][k] == new['stats'][k] for k in effects), (case, 'effects')
        assert old['stage_spine']['iterative_bake'] == new['stage_spine']['iterative_bake'], (case, 'Bake evidence')
        result['workloads'][case] = {
            'program_sha256': new['program_sha256'], 'state_sha256': state,
            'source_runs': len(runs), 'exact_state_runs_effects_bake_evidence': True,
            'schedule_sha256': hashlib.sha256(json.dumps(runs, separators=(',', ':')).encode()).hexdigest(),
            'logical_effects': {k: new['stats'][k] for k in effects},
            'work': {label: {'key_lookup_calls': r['key_lookup_calls'],
                            'absorption': r['neighbor_context']['absorption'],
                            'query': r['query_workers']['stats'],
                            'route_probes': r['stats'].get('constructor_cell_route_probes', 0)}
                     for label, r in (('control', old), ('candidate', new))}}
    proof = read(candidate / 'semantic-acceptance.json')
    assert proof['status'] == 'pass'
    assert proof['input_sha256']['cpu_values'] == result['workloads']['sum']['state_sha256']
    result['native_sum_acceptance'] = {'status': 'pass', 'sha256': sha(candidate / 'semantic-acceptance.json')}
    return result


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    control, candidate, validation, output = map(Path, sys.argv[1:])
    output.write_text(json.dumps(check(control, candidate, validation), indent=2) + '\n')
    print('Merged runtime: exact states, source Run summaries/effects, Bake evidence and native sum acceptance pass')
