#!/usr/bin/env python3
"""Read saved Cell ownership-partition executions; never launch a timing run."""
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
    return [[s[k] for k in keys] for s in report['steps']]


def neighbor(report):
    total = {}
    for rule in report['neighbor_context']['rules'].values():
        for key, value in rule['stats'].items():
            total[key] = total.get(key, 0) + value
    return total


def accesses(report):
    # Neighbor and PointPorts hits bypass key_lookup_calls. Negative shared
    # hits are a subset of shared_point_hits and must not be added again.
    return (report['key_lookup_calls'] + neighbor(report)['point_hits']
            + report['stats']['shared_point_hits'])


def collect(root, prior, output):
    result = {
        'control_commit': '06e1c090', 'control_executable_commit': 'aa2161e2',
        'scope': 'standalone Cell CPU, not native egglog', 'goal_achieved': False,
        'runtime_sha256': sha(root / 'runtime'), 'workloads': {},
        'limits': 'Work and semantic diagnostics, not throughput or CPU utilization evidence. '
                  'Total point accesses combine authoritative lookups and old cache hits; '
                  'they are not a cycle-weighted cost model. Residual sorting counters exclude '
                  'ordinary coordinator sorting; their delta is not net extra comparisons. '
                  'Capacities are not total allocations or peak RSS. Mixed Entry preparation '
                  'is included in search time, not separately in residual prepare_seconds.'}
    for name in ('sum', 'ray'):
        a, b = (read(p / name / 'report.json') for p in (prior, root))
        assert a['status'] == b['status'] == 'complete'
        assert a['program_sha256'] == b['program_sha256']
        assert sha(prior / name / 'state.json') == sha(root / name / 'state.json')
        assert signature(a) == signature(b)
        # Only these graph counters count moved reads/cache accesses, rather
        # than effects. Require every other graph counter to agree exactly.
        moved = {'residual_candidates', 'shared_point_requests',
                 'shared_point_hits', 'shared_negative_hits'}
        assert a['stats'].keys() == b['stats'].keys()
        for k in a['stats'].keys() - moved:
            assert a['stats'][k] == b['stats'][k], k
        assert accesses(a) == accesses(b)
        assert a['sieve'] == b['sieve']
        assert a['known_results'] == b['known_results']
        assert a['neighbor_context']['absorption'] == b['neighbor_context']['absorption']
        assert a['stage_spine']['stats']['routed_spine_seeds'] == b['stage_spine']['stats']['routed_spine_seeds']
        for k in a['publication'].keys() - {'parallel', 'neighbor_rows'}:
            assert a['publication'][k] == b['publication'][k], k
        old, new = (r['query_workers']['residual_expansion']['stats'] for r in (a, b))
        delivered = [r['entry_schedule']['stats']['consumer_seed_deliveries'] for r in (a, b)]
        assert delivered[0] - delivered[1] == new['partitioned_admitted']
        assert new['input_rows'] - old['input_rows'] == new['partitioned_entries']
        assert sum(new['partitioned_worker_entries']) + new['partitioned_inline_entries'] == new['partitioned_entries']
        assert new['partitioned_entries'] > 0 and sum(new['partitioned_worker_entries']) > 0
        result['workloads'][name] = {
            'runs': len(b['steps']), 'program_sha256': b['program_sha256'],
            'state_sha256': sha(root / name / 'state.json'),
            'before_report_sha256': sha(prior / name / 'report.json'),
            'after_report_sha256': sha(root / name / 'report.json'),
            'same_state_ordered_runs_effect_counters_sieve_absorption_and_total_point_accesses': True,
            'consumer_seed_deliveries': delivered,
            'total_point_accesses': [accesses(r) for r in (a, b)],
            'key_lookup_calls': [r['key_lookup_calls'] for r in (a, b)],
            'neighbor_totals': [neighbor(r) for r in (a, b)],
            'neighbor_publication': [r['neighbor_context']['publication'] for r in (a, b)],
            'neighbor_demanded_keys': [r['neighbor_context']['demanded_keys'] for r in (a, b)],
            'free_join': [r['free_join'] for r in (a, b)],
            'total_free_join_probes': [r['free_join']['entry_probes'] + w['admission_probes']
                                      for r, w in ((a, old), (b, new))],
            'residual_work_before': old, 'residual_work_after': new,
            'plan_capacity_bytes': [r['query_workers']['residual_expansion']['plan_capacity_bytes'] for r in (a, b)],
            'rule_run_capacity_bytes_after': b['query_workers']['rule_run_capacity_bytes'],
            'query_workers_before': a['query_workers']['stats'],
            'query_workers_after': b['query_workers']['stats'],
        }
    assert read(root / 'semantic-acceptance.json')['status'] == 'pass'
    assert sha(root / 'sum/state.json') == sha(root / 'semantic/run-values/state.json')
    result['sum_native_acceptance'] = {'status': 'pass', 'sha256': sha(root / 'semantic-acceptance.json')}
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: {'saved_seed_handoffs': v['residual_work_after']['partitioned_admitted'],
                         'new_worker_entries': sum(v['residual_work_after']['partitioned_worker_entries']),
                         'point_accesses': v['total_point_accesses']}
                      for k, v in result['workloads'].items()}, indent=2))


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    collect(*(Path(a) for a in sys.argv[1:]))
