#!/usr/bin/env python3
"""Check saved merged executions and distinguish overlapping takeovers."""
import hashlib
import json
from pathlib import Path
import sys


def read(p):
    return json.loads(p.read_text())


def sha(p):
    with p.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def schedule(r, executed=True):
    keys = ['ordinal', 'ruleset', 'path', 'iterations', 'epoch', 'logical_matches', 'changed']
    if executed:
        keys.append('executed_bindings')
    return [[s[k] for k in keys] for s in r['steps']]


def work(r):
    neighbor = r['neighbor_context']
    result = {
        'graph': r['stats'], 'key_lookup_calls': r['key_lookup_calls'],
        'free_join': r['free_join'], 'sieve': {k: v for k, v in r['sieve']['stats'].items() if k != 'per_rule'},
        'entry_seed_deliveries': r['entry_schedule']['stats']['consumer_seed_deliveries'],
        'neighbor_demanded_keys': neighbor['demanded_keys'],
        'neighbor_publication': neighbor['publication'],
        'neighbor_point_hits': sum(x['stats']['point_hits'] for x in neighbor['rules'].values()),
        'absorption': {k: v for k, v in neighbor['absorption']['stats'].items() if k != 'pending'},
        'history_sealing': {k: v for k, v in r['stage_spine']['stats'].items() if k.startswith('history_seal')},
        'publication': {k: v for k, v in r['publication'].items() if k != 'parallel'},
    }
    workers = r.get('query_workers', {})
    result['partitioned_queries'] = {k: v for k, v in workers.get('residual_expansion', {}).get('stats', {}).items()
                                     if k.startswith('partitioned_')}
    result['parallel_publication'] = {k: v for k, v in r['publication'].get('parallel', {}).items()
                                      if k in ('rows', 'inline_rows', 'pool_calls', 'worker_rows',
                                               'change_buffer_growths', 'peak_retained_change_bytes')}
    return result


def check(root, old, output):
    result = {'parents': ['b2428807', '17d8dbe6'], 'merge_base': '50316626',
              'scope': 'standalone Cell CPU, not native egglog', 'runtime_sha256': sha(root / 'runtime'),
              'incoming_runtime_sha256': sha(root / 'reference-runtime'),
              'limits': 'Complete work/semantic checks, no new timing campaign. Raytrace is a relative regression check. '
                        'Inline domains and point projection overlap worker takeover; their savings cannot be added. '
                        'Task/header capacities are not allocator totals or a throughput claim.', 'cases': {}}
    for case in ('sum', 'ray'):
        paths = {'parallel_parent': old / case}
        paths.update({lane: root / (lane + '-' + case) for lane in ('reference', 'point', 'parallel')})
        reports = {lane: read(p / 'report.json') for lane, p in paths.items()}
        ref = reports['reference']
        for lane, r in reports.items():
            assert r['status'] == 'complete' and r['program_sha256'] == ref['program_sha256']
            assert sha(paths[lane] / 'state.json') == sha(paths['reference'] / 'state.json'), (case, lane)
            assert schedule(r, False) == schedule(ref, False), (case, lane)
            for k in ('function_updates', 'unions', 'logical_facts_created'):
                assert r['stats'][k] == ref['stats'][k], (case, lane, k)
            if lane != 'parallel_parent':
                assert schedule(r) == schedule(ref), (case, lane, 'execution order')
                assert r['neighbor_context']['absorption']['stats'] == ref['neighbor_context']['absorption']['stats']
                for k in ('added_keys', 'probes', 'rejected', 'dependency_rows'):
                    assert r['sieve']['stats'][k] == ref['sieve']['stats'][k], (case, lane, k)
        combined = reports['parallel']
        assert combined['query_workers']['residual_expansion']['stats']['partitioned_entries'] > 0
        if case == 'ray':
            assert combined['publication']['parallel']['pool_calls'] > 0
            assert combined['neighbor_context']['absorption']['stats']['mixed_absorbed'] > 0
        result['cases'][case] = {'runs': len(ref['steps']), 'program_sha256': ref['program_sha256'],
                                'state_sha256': sha(paths['reference'] / 'state.json'),
                                'same_state_logical_runs_and_committed_effects': True,
                                'same_executed_runs_and_absorption_as_incoming': True,
                                'lanes': {lane: {'report_sha256': sha(paths[lane] / 'report.json'), 'work': work(r)}
                                          for lane, r in reports.items()}}
    acceptance = read(root / 'semantic-acceptance.json')
    assert acceptance['status'] == 'pass'
    assert acceptance['input_sha256']['cpu_values'] == sha(root / 'parallel-sum/state.json')
    result['native_sum_acceptance'] = {'status': 'pass', 'sha256': sha(root / 'semantic-acceptance.json')}
    output.write_text(json.dumps(result, indent=2) + '\n')
    print('pass: merged states, ordered Runs, actual effects and incoming absorption')


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    check(*map(Path, sys.argv[1:]))
