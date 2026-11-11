#!/usr/bin/env python3
"""Verify saved winner-completion runs against their exact publication control."""
import json
from pathlib import Path
import runpy
import sys


def main(root, prior, output):
    base = runpy.run_path(str(Path(__file__).with_name('collect.py')))
    read, sha, signature = (base[k] for k in ('read', 'sha', 'signature'))
    result = {'control_commit':'73c40b25', 'scope':'standalone Cell CPU, not native egglog',
              'runtime_sha256':sha(root / 'runtime'), 'goal_achieved':False, 'workloads':{},
              'limits':'Work diagnostics, not timing or CPU utilization evidence. Tasks own existing vectors; '
                       'new task capacity excludes existing answer buffers and pool bookkeeping. '
                       'Per-task seconds are wall residence. Single-rule completion remains inline.'}
    for name in ('sum', 'ray'):
        a, b = read(prior / name / 'report.json'), read(root / name / 'report.json')
        assert a['status'] == b['status'] == 'complete'
        assert a['program_sha256'] == b['program_sha256']
        assert sha(prior / name / 'state.json') == sha(root / name / 'state.json')
        assert signature(a) == signature(b)
        for key in ('stats', 'key_lookup_calls', 'sieve', 'free_join', 'indexed_columns', 'entry_schedule'):
            assert a[key] == b[key], key
        for key in a['publication']:
            if key != 'parallel':
                assert a['publication'][key] == b['publication'][key], key
        old = a['query_workers']['residual_expansion']['stats']
        new = b['query_workers']['residual_expansion']['stats']
        for key in ('entries', 'answers', 'input_rows', 'filter_probes', 'filter_rejected',
                    'admission_probes', 'admission_rejected', 'expansion_rows', 'row_reads',
                    'point_reads', 'queued_row_owners', 'order_comparisons', 'merge_capacity_bytes'):
            assert old[key] == new[key], (key, old[key], new[key])
        assert new['merge_inline_tasks'] + sum(new['merge_worker_tasks']) == new['merge_tasks']
        if name == 'ray':
            assert new['merge_pool_calls'] > 0 and sum(new['merge_worker_rows']) > 0
        result['workloads'][name] = {
            'runs':len(b['steps']), 'program_sha256':b['program_sha256'],
            'state_sha256':sha(root / name / 'state.json'),
            'before_report_sha256':sha(prior / name / 'report.json'),
            'after_report_sha256':sha(root / name / 'report.json'),
            'same_state_ordered_runs_graph_queries_filters_publication_and_comparisons':True,
            'plan_capacity_bytes_before':a['query_workers']['residual_expansion']['plan_capacity_bytes'],
            'plan_capacity_bytes_after':b['query_workers']['residual_expansion']['plan_capacity_bytes'],
            'residual_completion':{k:v for k,v in new.items() if k.startswith('merge_') or k == 'order_comparisons'},
        }
    assert read(root / 'semantic-acceptance.json')['status'] == 'pass'
    assert sha(root / 'semantic/run-values/state.json') == sha(root / 'sum/state.json')
    result['sum_native_acceptance'] = {'status':'pass', 'sha256':sha(root / 'semantic-acceptance.json')}
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    main(*(Path(a) for a in sys.argv[1:]))
