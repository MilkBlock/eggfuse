#!/usr/bin/env python3
"""Collect frozen throughput, actual worker work, sampling and semantic evidence."""
import hashlib
import json
from pathlib import Path
import runpy
import statistics
import sys


def read(p):
    return json.loads(p.read_text())


def sha(p):
    with p.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def collect(root, output):
    helpers = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'raytrace-parallel/collect.py'))
    parse = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'raytrace-thread-bottlenecks/collect.py'))['sample_threads']
    s = read(root / 'timing/samples.json')
    assert s.get('finished_at_utc') and 'failure' not in s
    reference = s['semantic_reference']
    result = {'control_commit': '50316626', 'scope': 'standalone Cell CPU, not native egglog',
              'goal_achieved': False, 'evidence_sha256': {}, 'lanes': {}, 'comparisons': {},
              'limits': 'Three interleaved samples per lane, one warmup; all retained. Background system/application activity was present. Whole-process average cores includes load/export and is not inference utilization. Eight workers also raise the filter admission threshold from 1024 to 2048 rows. No thread scaling or overall speedup established.'}
    effects = ('constructor_requests', 'function_updates', 'unions', 'logical_facts_created')
    actual = {k: s['lanes']['point4']['samples'][0]['stats'][k] for k in effects}
    for name, lane in s['lanes'].items():
        result['lanes'][name] = {'args': lane['args'], 'runtime_sha256': lane['runtime_sha256'],
                                 'program_sha256': lane['program_file_sha256'], 'samples': [], 'warmups': []}
        target = result['lanes'][name]
        for kind, rows in [('samples', lane['samples']), ('warmups', lane['warmup_samples'])]:
            for r in rows:
                assert {k: r[k] for k in reference} == reference and r['runs'] == 16883
                assert {k: r['stats'][k] for k in effects} == actual
                if name.startswith('filter'):
                    c = r['sieve']['parallel']['stats']
                    assert sum(c['worker_rows']) == c['rows']
                    assert sum(c['worker_probes']) == c['probes'] and c['probes'] > 0
                    assert r['sieve']['stats'] == s['lanes']['point4']['samples'][0]['sieve']['stats']
                target[kind].append({**{k: r[k] for k in ('iteration', 'inference_seconds', 'process_wall_seconds',
                    'process_user_seconds', 'process_system_seconds', 'phases')},
                    'process_average_cores': (r['process_user_seconds'] + r['process_system_seconds']) / r['process_wall_seconds'],
                    'entry_filters': r['sieve'].get('parallel')})
        target['median_inference_seconds'] = statistics.median(r['inference_seconds'] for r in lane['samples'])
    for a,b in [('point4','filter4'), ('serial','filter4'), ('filter4','filter8')]:
        result['comparisons'][b + '_over_' + a] = helpers['paired_ratio'](
            [r['inference_seconds'] for r in s['lanes'][a]['samples']],
            [r['inference_seconds'] for r in s['lanes'][b]['samples']])
    diagnostic = read(root / 'profile/diagnostic.json')
    assert {k: diagnostic[k] for k in reference} == reference
    assert diagnostic['runtime_sha256'] == s['lanes']['filter4']['runtime_sha256']
    assert sha(root / 'profile/stacks.txt') == diagnostic['sample']['stacks_sha256']
    threads = parse(root / 'profile/stacks.txt')
    result['profile'] = {'sampling': diagnostic['sample'],
        'main_inference_inclusive': threads[0]['inference_inclusive'],
        'workers': [{'samples': t['samples'], 'condition_wait_samples': t['inclusive'].get('__psynch_cvwait', 0)} for t in threads[1:]],
        'limits': 'Separate five-second sampled window; stack residence, not CPU time. Inclusive counts overlap; logging and sampling perturb the run.'}
    acceptance = read(root / 'semantic-acceptance.json')
    assert acceptance['status'] == 'pass'
    assert sha(root / 'sum-on/state.json') == sha(root / 'sum-off/state.json') == sha(root / 'semantic/run-values/state.json')
    result['semantic'] = {'raytrace_relative_reference': reference, 'actual_effects': actual,
                           'sum_native_acceptance': 'pass', 'sum_state_sha256': sha(root / 'sum-on/state.json')}
    for name in ['timing/samples.json', 'profile/diagnostic.json', 'profile/stacks.txt', 'semantic-acceptance.json']:
        result['evidence_sha256'][name] = sha(root / name)
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'medians': {k:v['median_inference_seconds'] for k,v in result['lanes'].items()},
                      'comparisons':result['comparisons'],'workers':result['profile']['workers']},indent=2))


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    collect(Path(sys.argv[1]), Path(sys.argv[2]))
