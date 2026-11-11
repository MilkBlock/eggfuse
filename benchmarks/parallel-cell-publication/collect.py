#!/usr/bin/env python3
"""Compare complete saved publication executions; do not launch a timing run."""
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


def collect(root, prior, output):
    result = {'control_commit': 'c6823564', 'scope': 'standalone Cell CPU, not native egglog',
              'goal_achieved': False, 'runtime_sha256': sha(root / 'runtime'), 'workloads': {},
              'limits': 'Work and semantic diagnostics, no speed or CPU utilization claim. '
                        'Task time is wall residence, not CPU time. Capacity counts exclude '
                        'existing index contents, allocator metadata and pool bookkeeping. '
                        'Existing tables are moved, not cloned; column notification buffers '
                        'retain empty capacity between Runs. A single large table is one task.'}
    for name in ('sum', 'ray'):
        old, new = prior / (name + '-checked'), root / name
        a, b = read(old / 'report.json'), read(new / 'report.json')
        assert a['status'] == b['status'] == 'complete'
        assert a['program_sha256'] == b['program_sha256']
        assert sha(old / 'state.json') == sha(new / 'state.json')
        assert signature(a) == signature(b)
        assert a['stats'] == b['stats'] and a['key_lookup_calls'] == b['key_lookup_calls']
        for field in ('sieve', 'free_join', 'indexed_columns', 'entry_schedule'):
            assert a[field] == b[field], field
        published = b['publication'].copy()
        work = published.pop('parallel')
        assert a['publication'] == published
        assert work['enabled']
        if name == 'ray':
            assert work['pool_calls'] > 0
        assert sum(work['worker_rows']) + work['inline_rows'] == work['rows']
        assert work['rows'] <= published['headers'] - published['header_only']
        assert work['row_reads'] <= published['row_reads']
        result['workloads'][name] = {
            'program_sha256': b['program_sha256'], 'state_sha256': sha(new / 'state.json'),
            'before_report_sha256': sha(old / 'report.json'), 'after_report_sha256': sha(new / 'report.json'),
            'runs': len(b['steps']), 'same_graph_counters_and_key_reads': True,
            'same_publication_sieve_free_join_entry_schedule_and_index_coverage': True,
            'total_publication': published, 'parallel_publication': work,
        }
    assert read(root / 'semantic-acceptance.json')['status'] == 'pass'
    assert sha(root / 'sum/state.json') == sha(root / 'semantic/run-values/state.json')
    result['sum_native_acceptance'] = {'status': 'pass', 'report_sha256': sha(root / 'semantic-acceptance.json')}
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: {'rows_on_workers': sum(v['parallel_publication']['worker_rows']),
                         'total_publication_rows': v['total_publication']['headers'] - v['total_publication']['header_only']}
                      for k, v in result['workloads'].items()}, indent=2))


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    collect(*(Path(arg) for arg in sys.argv[1:]))
