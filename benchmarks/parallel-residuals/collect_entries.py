#!/usr/bin/env python3
"""Check the direct Entry takeover against cef7db18's saved execution."""
import json
from pathlib import Path
import runpy
import sys

helpers = runpy.run_path(str(Path(__file__).with_name('collect.py')))
read, sha, signature = (helpers[k] for k in ('read', 'sha', 'signature'))


def collect(root, prior, output):
    result = {'control_commit': 'cef7db18', 'scope': 'standalone Cell CPU, not native egglog',
              'goal_achieved': False, 'runtime_sha256': sha(root / 'runtime'), 'workloads': {},
              'limits': 'Complete work/semantic checks, no throughput campaign or utilization claim. '
                        'Preparation now includes gathering borrowed Entry rows; prior preparation '
                        'excluded Scheduler Seed creation. Phase numbers are not comparable. '
                        'Capacity totals exclude Instance payloads, allocator headers and pool bookkeeping.'}
    preserved = ('entries', 'admission_probes', 'admission_rejected', 'admission_rows',
                 'expansion_probes', 'expansion_rows', 'index_rows_examined', 'row_reads',
                 'point_reads', 'answers')
    for name in ('sum', 'ray'):
        old, new = prior / (name + '-final'), root / name
        a, b = read(old / 'report.json'), read(new / 'report.json')
        assert a['status'] == b['status'] == 'complete'
        assert a['program_sha256'] == b['program_sha256']
        assert sha(old / 'state.json') == sha(new / 'state.json')
        assert signature(a) == signature(b)
        assert a['stats'] == b['stats'] and a['key_lookup_calls'] == b['key_lookup_calls']
        assert a['sieve']['stats'] == b['sieve']['stats']
        assert a['publication'] == b['publication'] and a['indexed_columns'] == b['indexed_columns']
        before = a['query_workers']['residual_expansion']['stats']
        after = b['query_workers']['residual_expansion']['stats']
        assert {k: before[k] for k in preserved} == {k: after[k] for k in preserved}
        schedule = [r['entry_schedule']['stats'] for r in (a, b)]
        eliminated = schedule[0]['consumer_seed_deliveries'] - schedule[1]['consumer_seed_deliveries']
        assert eliminated == after['direct_entries'] > 0
        assert after['input_rows'] == after['entries'] + after['filter_rejected']
        result['workloads'][name] = {
            'program_sha256': b['program_sha256'], 'state_sha256': sha(new / 'state.json'),
            'runs': len(b['steps']), 'before_report_sha256': sha(old / 'report.json'),
            'after_report_sha256': sha(new / 'report.json'),
            'same_graph_counters_and_total_key_lookups': True, 'same_sieve_counts': True,
            'same_publication_counts_and_index_coverage': True,
            'consumer_seed_deliveries': [r['consumer_seed_deliveries'] for r in schedule],
            'consumer_projection_slots': [r['borrowed_slots'] for r in schedule],
            'handoffs_omitted': eliminated,
            'work_before': before, 'work_after': after,
        }
    assert read(root / 'semantic-acceptance.json')['status'] == 'pass'
    assert sha(root / 'sum/state.json') == sha(root / 'semantic/run-values/state.json')
    result['sum_native_acceptance'] = {'status': 'pass', 'report_sha256': sha(root / 'semantic-acceptance.json')}
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: {'handoffs_omitted': v['handoffs_omitted'], 'runs': v['runs']}
                      for k, v in result['workloads'].items()}, indent=2))


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    collect(*(Path(arg) for arg in sys.argv[1:]))
