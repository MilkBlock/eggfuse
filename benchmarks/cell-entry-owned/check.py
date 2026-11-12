#!/usr/bin/env python3
"""Check actual Cell CPU takeover against the frozen 11056467 execution."""
import hashlib
import json
from pathlib import Path
import statistics
import sys


def read(path):
    return json.loads(path.read_text())


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def collect(root, previous):
    result = {'scope': 'actual standalone Cell CPU, not native egglog performance',
              'control_commit': '11056467', 'workloads': {}}
    runs = ['ordinal', 'ruleset', 'path', 'iterations', 'epoch',
            'logical_matches', 'executed_bindings', 'changed']
    effects = ['constructor_requests', 'constructor_reused', 'logical_facts_created',
               'function_updates', 'union_requests', 'unions', 'bindings']
    for case in ['sum', 'ray']:
        old = previous / f'candidate-{case}'
        new = root / f'candidate-{case}'
        a, b = read(old / 'report.json'), read(new / 'report.json')
        assert a['status'] == b['status'] == 'complete'
        assert a['program_sha256'] == b['program_sha256']
        state = sha(new / 'state.json')
        assert state == sha(old / 'state.json')
        assert [[s[k] for k in runs] for s in a['steps']] == [[s[k] for k in runs] for s in b['steps']]
        assert [a['stats'][k] for k in effects] == [b['stats'][k] for k in effects]
        x, y = (r['query_workers']['stats'] for r in (a, b))
        assert x['entry_headers'] - y['entry_headers'] == y['entry_range_rows'] > 0
        assert y['execution']['units']['rows'] == b['stats']['unit_prepared_consumed'] > 0
        assert b['stats']['unit_prepared_stale'] == 0
        if case == 'ray':
            assert b['stats']['unit_registry_installs'] > 0
        samples = read(root / f'timing-{case}/samples.json')
        assert samples.get('finished_at_utc') and 'failure' not in samples
        timing = {}
        for lane, data in samples['lanes'].items():
            assert data['runtime_sha256'] == sha(root / f'{lane}-runtime')
            assert all(s['state_sha256'] == state for s in data['samples'])
            fields = ['inference_seconds', 'process_wall_seconds', 'process_user_seconds',
                      'process_system_seconds', 'phases']
            timing[lane] = {k: data[k] for k in ['args', 'runtime_sha256', 'program_file_sha256']}
            timing[lane]['samples'] = [{k: s[k] for k in fields} for s in data['samples']]
            timing[lane]['median_seconds'] = statistics.median(s['inference_seconds'] for s in data['samples'])
            timing[lane]['process_cores_median'] = statistics.median(
                (s['process_user_seconds'] + s['process_system_seconds']) / s['process_wall_seconds']
                for s in data['samples'])
        result['workloads'][case] = {'program_sha256': b['program_sha256'], 'state_sha256': state,
            'runs': len(b['steps']), 'exact_final_state_and_run_summaries': True,
            'logical_effects_equal': True,
            'old_entry_headers': x['entry_headers'], 'entry_headers': y['entry_headers'],
            'ranges': {k: v for k, v in y.items() if k.startswith('entry_range_')},
            'prepared_units': y['execution']['units'],
            'unit_adoption_and_registration': {k: v for k, v in b['stats'].items() if k.startswith('unit_')},
            'timing': timing}
    proof = read(root / 'semantic-acceptance.json')
    assert proof['status'] == 'pass'
    assert proof['input_sha256']['cpu_values'] == result['workloads']['sum']['state_sha256']
    result['semantic_acceptance'] = {'status': 'pass', 'sha256': sha(root / 'semantic-acceptance.json')}
    return result


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    result = collect(Path(sys.argv[1]), Path(sys.argv[2]))
    Path(sys.argv[3]).write_text(json.dumps(result, indent=2) + '\n')
    print('Entry ranges, actual Unit rows, source ordering and semantic acceptance pass')
