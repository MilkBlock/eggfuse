#!/usr/bin/env python3
"""Check Run-wide Cell dispatch against saved 15b0b4c1 executions, without timing."""
import json
from pathlib import Path
import runpy
import sys

helpers = runpy.run_path(str(Path(__file__).with_name('collect.py')))
read, sha, signature = (helpers[k] for k in ('read', 'sha', 'signature'))


def collect(root, prior, output):
    result = {
        'control_commit': '15b0b4c1',
        'scope': 'standalone Cell CPU, not native egglog',
        'goal_achieved': False,
        'runtime_sha256': sha(root / 'runtime'),
        'limits': 'Work and semantic diagnostics only; no throughput/utilization claim. '
                  'New headers, result capacities and task times can include point queries '
                  'in the same Run/chunk. Old residual-only fields are not directly comparable. '
                  'Capacities exclude instance payloads, allocator metadata and pool bookkeeping; '
                  'totals are not simultaneously live memory.',
        'workloads': {},
    }
    preserved = ('input_rows', 'entries', 'admission_probes', 'admission_rejected',
                 'admission_rows', 'expansion_probes', 'expansion_rows', 'row_reads',
                 'index_rows_examined', 'point_reads', 'answers', 'filter_probes',
                 'filter_rejected', 'direct_entries', 'direct_batches')
    dispatch = ('batches', 'chunks', 'entries', 'answers', 'cell_instances', 'multi_entry_cells',
                'cross_rule_cells', 'cell_task_records', 'cell_task_probes', 'cell_task_links',
                'entry_buffer_bytes', 'peak_cell_queue_bytes', 'peak_cell_task_bytes',
                'compiled_cell_code_bytes', 'answer_buffer_allocations', 'output_buffer_capacity')
    for name in ('sum', 'ray'):
        old, new = prior / name, root / (name + '-checked')
        a, b = read(old / 'report.json'), read(new / 'report.json')
        assert a['status'] == b['status'] == 'complete'
        assert a['program_sha256'] == b['program_sha256']
        assert sha(old / 'state.json') == sha(new / 'state.json')
        assert signature(a) == signature(b)
        assert a['stats'] == b['stats'] and a['key_lookup_calls'] == b['key_lookup_calls']
        assert a['sieve']['stats'] == b['sieve']['stats']
        assert a['publication'] == b['publication'] and a['indexed_columns'] == b['indexed_columns']
        assert a['entry_schedule']['stats'] == b['entry_schedule']['stats']
        before = a['query_workers']['residual_expansion']['stats']
        after = b['query_workers']['residual_expansion']['stats']
        assert {k: before[k] for k in preserved} == {k: after[k] for k in preserved}
        assert after['input_rows'] == after['queued_row_owners']
        assert after['input_rows'] == after['entries'] + after['filter_rejected']
        assert sum(after['worker_entries']) + after['coordinator_entries'] == after['entries']
        assert 0 < after['mixed_runs'] <= after['merged_runs'] < before['batches']
        result['workloads'][name] = {
            'program_sha256': b['program_sha256'], 'state_sha256': sha(new / 'state.json'),
            'runs': len(b['steps']), 'before_report_sha256': sha(old / 'report.json'),
            'after_report_sha256': sha(new / 'report.json'),
            'same_graph_counters_and_total_key_lookups': True,
            'same_sieve_counts_publication_index_coverage_and_entry_schedule': True,
            'same_residual_query_work': True,
            'work_before': before, 'work_after': after,
            'shared_dispatch': {k: [r['query_workers']['stats'][k] for r in (a, b)] for k in dispatch},
            'new_plan_capacity_bytes': b['query_workers']['residual_expansion']['plan_capacity_bytes'],
        }
    assert read(root / 'semantic-acceptance.json')['status'] == 'pass'
    assert sha(root / 'sum-checked/state.json') == sha(root / 'semantic/run-values/state.json')
    result['sum_native_acceptance'] = {'status': 'pass', 'report_sha256': sha(root / 'semantic-acceptance.json')}
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: {'source_batches': v['work_before']['batches'],
                         'merged_runs': v['work_after']['merged_runs'],
                         'mixed_runs': v['work_after']['mixed_runs']}
                      for k, v in result['workloads'].items()}, indent=2))


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    collect(*(Path(arg) for arg in sys.argv[1:]))
