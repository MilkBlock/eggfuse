#!/usr/bin/env python3
"""Verify actual Cell CPU takeover against the frozen source control."""
import hashlib
import json
from pathlib import Path
import runpy
import statistics
import sys


def read(p):
    return json.loads(p.read_text())


def sha(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def collect(root):
    result = {'scope': 'actual standalone Cell CPU; not native egglog runtime performance',
              'control_commit': 'b47cb0fa',
              'runtime_sha256': sha(root / 'runtime'),
              'control_runtime_sha256': sha(root / 'control-runtime'), 'workloads': {}}
    fields = ('ordinal', 'ruleset', 'path', 'iterations', 'epoch', 'logical_matches', 'executed_bindings', 'changed')
    effects = ('constructor_requests', 'constructor_reused', 'logical_facts_created',
               'function_updates', 'union_requests', 'unions', 'bindings')
    for case in ('sum', 'ray'):
        a, b = [read(root / lane / 'report.json') for lane in (f'control-{case}', case)]
        assert a['status'] == b['status'] == 'complete'
        assert a['program_sha256'] == b['program_sha256']
        state = sha(root / case / 'state.json')
        assert state == sha(root / f'control-{case}' / 'state.json')
        assert [[s[k] for k in fields] for s in a['steps']] == [[s[k] for k in fields] for s in b['steps']]
        assert {k: a['stats'][k] for k in effects} == {k: b['stats'][k] for k in effects}
        w = b['cell_execution']['runtime']['stats']['writes']
        assert w['candidates'] - w['rows'] == w['duplicate_targets']
        assert w['candidates'] - w['row_writes'] == w['invalidated']
        assert w['logical_improvements'] - w['row_writes'] == w['superseded_improvements']
        assert w['writer_allocations'] + w['writer_reuses'] == w['row_writes']
        assert w['worker_rows'] == w['rows']
        assert w['fallback_batches'] == 0
        if case == 'ray':
            assert w['worker_rows'] > 0 and w['duplicate_targets'] > 0 and w['writer_reuses'] > 0
        samples = read(root / f'timing-{case}' / 'samples.json')
        timing = {}
        for lane, data in samples['lanes'].items():
            expected = result['runtime_sha256' if lane == 'candidate' else 'control_runtime_sha256']
            assert expected == data['runtime_sha256']
            assert all(s['state_sha256'] == state for s in data['samples'])
            times = [s['inference_seconds'] for s in data['samples']]
            timing[lane] = {
                'args': data['args'], 'program_file_sha256': data['program_file_sha256'],
                'samples': [{k: s[k] for k in ('iteration', 'inference_seconds', 'process_wall_seconds', 'phases',
                             'state_sha256', 'schedule_sha256')} for s in data['samples']],
                'inference_median_seconds': statistics.median(times),
                'phase_medians_seconds': {k: statistics.median(s['phases'][k] for s in data['samples'])
                                         for k in data['samples'][0]['phases']}}
        result['workloads'][case] = {
            'state_sha256': state, 'program_sha256': b['program_sha256'], 'runs': len(b['steps']),
            'exact_final_state_and_run_summaries': True, 'logical_effects_equal': True,
            'writes': w, 'single_write_total': b['stats']['single_writes'], 'timing': timing}
    proof = read(root / 'semantic-acceptance.json')
    assert proof['status'] == 'pass'
    assert proof['input_sha256']['cpu_values'] == result['workloads']['sum']['state_sha256']
    result['semantic_acceptance'] = {'status': 'pass', 'sha256': sha(root / 'semantic-acceptance.json')}
    profile = runpy.run_path(str(Path(__file__).parents[1] / 'cell-peer-results/waits.py'))['profile']
    result['wall_profiles'] = []
    for name in ('profile', 'profile-clean'):
        p = profile(root / name)
        assert p['runtime_sha256'] == result['runtime_sha256']
        assert p['state_sha256'] == result['workloads']['ray']['state_sha256']
        p['limits'] = ('Partial wall-stack sample, not CPU utilization; logging and sampling perturb execution. '
                       'The first profile overlapped briefly with the Python semantic validator; '
                       'profile-clean ran after that validator completed. These windows do not prove a utilization improvement.')
        p['name'] = name
        result['wall_profiles'].append(p)
    return result


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    result = collect(Path(sys.argv[1]))
    Path(sys.argv[2]).write_text(json.dumps(result, indent=2) + '\n')
    print('actual row writes, local invalidations, source effects, Run summaries and native sum-bits contract pass')
