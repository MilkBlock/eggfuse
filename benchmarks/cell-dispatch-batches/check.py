#!/usr/bin/env python3
"""Verify the actual CPU dispatch takeover and retain all timing samples."""
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
    result = {'scope': 'actual standalone Cell CPU, not native egglog runtime performance',
              'control_commit': '534bc384', 'workloads': {}}
    keys = ('ordinal', 'ruleset', 'path', 'iterations', 'epoch', 'logical_matches', 'executed_bindings', 'changed')
    effects = ('constructor_requests', 'constructor_reused', 'logical_facts_created',
               'function_updates', 'union_requests', 'unions', 'bindings')
    for case in ('sum', 'ray'):
        reports = [read(root / f'{lane}-{case}/report.json') for lane in ('control', 'candidate')]
        a, b = reports
        assert a['status'] == b['status'] == 'complete'
        assert a['program_sha256'] == b['program_sha256']
        state = sha(root / f'candidate-{case}/state.json')
        assert state == sha(root / f'control-{case}/state.json')
        assert [[s[k] for k in keys] for s in a['steps']] == [[s[k] for k in keys] for s in b['steps']]
        assert {k: a['stats'][k] for k in effects} == {k: b['stats'][k] for k in effects}
        work = b['cell_execution']['runtime']['stats']['births']
        queue = b['cell_execution']['runtime']['stats']['scheduler']
        assert work['unit_candidates'] == work['unit_inserts'] + work['unit_invalidated']
        assert work['unit_worker_rows'] <= work['unit_candidates']
        assert work['worker_batches'] <= queue['batches']
        assert b['cell_execution']['local_construction']['synchronous_single_cell_dispatch'] is False
        if case == 'ray':
            assert work['unit_worker_rows'] > 0 and work['unit_invalidated'] > 0
        samples = read(root / f'timing-{case}/samples.json')
        assert samples.get('finished_at_utc') and 'failure' not in samples
        timing = {}
        for lane, data in samples['lanes'].items():
            assert data['runtime_sha256'] == sha(root / f'{lane}-runtime')
            assert all(s['state_sha256'] == state for s in data['samples'])
            selected = ('inference_seconds', 'process_wall_seconds', 'process_user_seconds', 'process_system_seconds', 'phases')
            timing[lane] = {k: data[k] for k in ('args', 'runtime_sha256', 'program_file_sha256')}
            timing[lane]['samples'] = [{k: s[k] for k in selected} for s in data['samples']]
            timing[lane]['median_seconds'] = statistics.median(s['inference_seconds'] for s in data['samples'])
        result['workloads'][case] = {'program_sha256': b['program_sha256'], 'state_sha256': state,
            'runs': len(b['steps']), 'exact_final_state_and_run_summaries': True, 'logical_effects_equal': True,
            'work': {lane: r['cell_execution']['runtime']['stats'] for lane, r in zip(('control', 'candidate'), reports)},
            'timing': timing}
    proof = read(root / 'semantic-acceptance.json')
    assert proof['status'] == 'pass'
    assert proof['input_sha256']['cpu_values'] == result['workloads']['sum']['state_sha256']
    result['semantic_acceptance'] = {'status': 'pass', 'sha256': sha(root / 'semantic-acceptance.json')}
    if (root / 'profile').exists():
        profile = runpy.run_path(str(Path(__file__).parents[1] / 'cell-peer-results/waits.py'))['profile']
        p = profile(root / 'profile')
        assert p['runtime_sha256'] == sha(root / 'candidate-runtime')
        assert p['state_sha256'] == result['workloads']['ray']['state_sha256']
        result['wall_profile'] = p
    return result


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    Path(sys.argv[2]).write_text(json.dumps(collect(Path(sys.argv[1])), indent=2) + '\n')
    print('source effects, Run summaries, actual Unit rows and native sum-bits contract pass')
