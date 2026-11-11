#!/usr/bin/env python3
"""Check complete saved runs and account for Cell condition publication work."""
import hashlib
import json
from pathlib import Path
import sys


def read(path):
    return json.loads(path.read_text())


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def check(root, prior, output):
    result = {'control_commit': '77f0dc81', 'scope': 'standalone Cell CPU',
              'runtime_sha256': sha(root / 'runtime'), 'workloads': {},
              'limits': 'Complete work/semantic executions, not throughput evidence. '
                        'Worker rows are transferred existing summary work, not saved operations '
                        'or CPU utilization. Scratch/header bytes exclude allocator overhead.'}
    keys = ('ordinal', 'ruleset', 'path', 'iterations', 'epoch', 'logical_matches', 'executed_bindings', 'changed')
    for case in ('sum', 'ray'):
        old, new = prior / case, root / case
        a, b = read(old / 'report.json'), read(new / 'report.json')
        assert a['status'] == b['status'] == 'complete'
        assert a['program_sha256'] == b['program_sha256']
        assert sha(old / 'state.json') == sha(new / 'state.json')
        assert [[s[k] for k in keys] for s in a['steps']] == [[s[k] for k in keys] for s in b['steps']]
        for key in ('stats', 'key_lookup_calls', 'maintenance', 'free_join', 'entry_schedule',
                    'known_results', 'neighbor_context', 'indexed_columns', 'repair_ports'):
            assert a[key] == b[key], (case, key)
        for key in a['sieve']:
            assert a['sieve'][key] == b['sieve'][key], (case, 'sieve', key)
        for key in a['publication'].keys() - {'parallel'}:
            assert a['publication'][key] == b['publication'][key], (case, key)
        # Scheduling changes task placement, capacities and residence times.
        for group in ('stats', 'residual_expansion'):
            u, v = a['query_workers'][group], b['query_workers'][group]
            if group == 'residual_expansion':
                u, v = u['stats'], v['stats']
            for key, count in u.items():
                if isinstance(count, int) and not any(s in key for s in ('capacity', 'bytes', 'growth', 'allocation')):
                    assert v[key] == count, (case, key)
        plan = b['sieve']['publication']
        for key in ('pending_group_rows', 'pending_support_keys', 'pending_tasks'):
            assert plan[key] == 0, (case, key)
        work = plan['stats']
        transferred = sum(work['worker_rows'])
        staged = work['direct_rows'] + work['dependency_rows']
        total = b['sieve']['stats']['update_rows'] + b['sieve']['stats']['dependency_rows']
        assert transferred <= staged <= total
        if case == 'ray':
            assert work['pool_calls'] > 0
            assert sum(n > 0 for n in work['worker_rows']) > 1
        else:
            assert not plan['compiled'] and plan['plan_payload_bytes'] == 0
        result['workloads'][case] = {
            'runs': len(b['steps']), 'program_sha256': b['program_sha256'],
            'state_sha256': sha(new / 'state.json'), 'before_report_sha256': sha(old / 'report.json'),
            'after_report_sha256': sha(new / 'report.json'),
            'same_state_ordered_runs_graph_queries_summaries_and_publication': True,
            'summary_updates_total': total, 'worker_summary_updates': transferred,
            'coordinator_summary_updates': total - transferred,
            'staged_inline_updates': staged - transferred,
            'condition_publication': plan,
        }
    accepted = read(root / 'semantic-acceptance.json')
    assert accepted['status'] == 'pass'
    assert accepted['input_sha256']['cpu_values'] == sha(root / 'sum/state.json')
    result['native_sum_acceptance'] = {'status': 'pass', 'sha256': sha(root / 'semantic-acceptance.json')}
    output.write_text(json.dumps(result, indent=2) + '\n')
    diagnostic = root / 'profile/diagnostic.json'
    if diagnostic.exists():
        sampled = read(diagnostic)
        assert sampled['runtime_sha256'] == result['runtime_sha256']
        assert sampled['state_sha256'] == result['workloads']['ray']['state_sha256']
        assert sampled['same_state_ordered_runs_and_graph_counts']
        main, *workers = sampled['threads']
        selected = ('Executor::matches', 'Scheduler::batches', 'publish_finished_tables',
                    'RhsFrame::execute', 'repair_selected', 'Workers::finish_run',
                    'replace_subscriptions', 'publish_staged')
        profile = {k: sampled[k] for k in ('scope', 'runtime_sha256', 'program_file_sha256',
                   'state_sha256', 'runs', 'stacks_sha256', 'limits')}
        profile['diagnostic_sha256'] = sha(diagnostic)
        profile['main_samples'] = main['samples']
        profile['main_selected_inclusive'] = {
            key: sum(n for s, n in main['inference_inclusive'].items() if s.endswith(key))
            for key in selected}
        profile['worker_parked'] = [
            {'thread': w['thread'], 'samples': w['samples'],
             'condition_wait_samples': w['inclusive'].get('__psynch_cvwait', 0),
             'condition_wait_fraction': w['inclusive'].get('__psynch_cvwait', 0) / w['samples']}
            for w in workers]
        output.with_name('profile.json').write_text(json.dumps(profile, indent=2) + '\n')
    print(json.dumps({k: {n: v[n] for n in ('runs', 'summary_updates_total', 'worker_summary_updates',
                                         'coordinator_summary_updates')} for k, v in result['workloads'].items()}, indent=2))


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    check(*map(Path, sys.argv[1:]))
