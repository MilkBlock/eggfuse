#!/usr/bin/env python3
"""Collect work and semantic evidence; deliberately no throughput comparison."""
import hashlib
import json
from pathlib import Path
import sys


def read(path):
    return json.loads(path.read_text())


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def signature(report):
    keys = ('ordinal', 'ruleset', 'path', 'iterations', 'epoch',
            'logical_matches', 'executed_bindings', 'changed')
    return [[step[key] for key in keys] for step in report['steps']]


def collect(root, sum_reference, ray_reference, sum_program, ray_program, output):
    result = {
        'control_commit': 'e2da3a05',
        'scope': 'standalone Cell CPU, not native egglog',
        'goal_achieved': False,
        'limits': 'Work/semantic diagnostics only; no new speed or utilization conclusion. '
                  'Ray control reuses the saved e2da3a05 profile with Entry filters enabled; '
                  'candidate leaves those filters on the coordinator. Timings are not compared. '
                  'Sum control is a feature-compiled but disabled development build. '
                  'Candidate DomainRc uses Arc even with its runtime flag disabled; its cost '
                  'requires a future normal timing comparison against the old build.',
        'runtime_sha256': sha(root / 'runtime-final'),
        'args': ['--repair-ports', '--entry-publications', '--cell-absorption',
                 '--query-workers', '4', '--parallel-residuals'],
        'workloads': {},
    }
    effects = ('constructor_requests', 'function_updates', 'unions', 'logical_facts_created')
    graph_keys = ('register_seeds', 'register_answers', 'register_expansion_rows',
                  'residual_candidates', 'shared_point_requests', 'shared_point_hits',
                  'shared_negative_hits')
    for name, reference, program in [('sum', sum_reference, sum_program),
                                      ('ray', ray_reference, ray_program)]:
        candidate = root / (name + '-final')
        before, after = read(reference / 'report.json'), read(candidate / 'report.json')
        assert before['status'] == after['status'] == 'complete'
        assert before['program_sha256'] == after['program_sha256']
        assert sha(reference / 'state.json') == sha(candidate / 'state.json')
        assert signature(before) == signature(after)
        assert {k: before['stats'][k] for k in effects} == {k: after['stats'][k] for k in effects}
        work = after['query_workers']['residual_expansion']
        assert work['enabled'] and work['stats']['expansion_rows'] > 0
        assert sum(work['stats']['worker_entries']) + work['stats']['coordinator_entries'] == work['stats']['entries']
        result['workloads'][name] = {
            'program_file_sha256': sha(program),
            'program_sha256': after['program_sha256'],
            'reference_report_sha256': sha(reference / 'report.json'),
            'candidate_report_sha256': sha(candidate / 'report.json'),
            'state_sha256': sha(candidate / 'state.json'),
            'runs': len(after['steps']),
            'run_signature_sha256': hashlib.sha256(json.dumps(signature(after), separators=(',', ':')).encode()).hexdigest(),
            'actual_effects': {k: after['stats'][k] for k in effects},
            'coordinator_free_join_probes': [before['free_join']['entry_probes'], after['free_join']['entry_probes']],
            'key_lookup_calls': [before['key_lookup_calls'], after['key_lookup_calls']],
            'graph_counts': {k: [before['stats'][k], after['stats'][k]] for k in graph_keys},
            'residual_expansion': work,
        }
    acceptance = read(root / 'semantic-acceptance.json')
    assert acceptance['status'] == 'pass'
    assert sha(root / 'sum-final/state.json') == sha(root / 'semantic-final/run-values/state.json')
    result['sum_native_acceptance'] = {'status': 'pass', 'report_sha256': sha(root / 'semantic-acceptance.json')}
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: {'runs': v['runs'], 'free_join': v['coordinator_free_join_probes'],
                         'lookups': v['key_lookup_calls']} for k, v in result['workloads'].items()}, indent=2))


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    collect(*(Path(arg) for arg in sys.argv[1:]))
