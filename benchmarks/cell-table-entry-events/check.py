#!/usr/bin/env python3
"""Account for independent Entry owners using already validated work exports."""
import json
from pathlib import Path
import sys


def read(path):
    return json.loads(path.read_text())


def run(control, candidate, checks, output):
    validation=read(candidate/'validation.json')
    proof=read(candidate/'semantic-acceptance.json')
    assert proof['status']=='pass'
    assert proof['input_sha256']['cpu_values']==validation['sum']['state_sha256']
    tested=read(checks/'validation.json')
    assert len(tested)==8 and all(t['exit_code']==0 for t in tested)
    result=dict(scope='actual standalone Cell CPU work and semantics; not timing',
                control=read(control/'manifest.json'),candidate=read(candidate/'manifest.json'),
                validation=validation,native_sum_status=proof['status'],checks=tested,workloads={})
    for case in ('sum','ray'):
        reports=[read(root/f'candidate-{case}/report.json') for root in (control,candidate)]
        a,b=reports
        entry_keys=('owner_entry_updates','owner_entry_nodes','predicate_checks','retired_packets',
                    'consumer_seed_deliveries','cell_entry_deliveries','row_reuse_checks')
        assert all(a['entry_schedule']['stats'][k]==b['entry_schedule']['stats'][k] for k in entry_keys)
        assert a['sieve']['stats']==b['sieve']['stats']
        for key in ('headers','column_rows','range_rows','neighbor_rows','view_column_rows'):
            assert a['publication'][key]==b['publication'][key]
        s=b['publication']['parallel']
        assert sum(s['worker_rows'])+s['inline_rows']==s['rows']
        assert sum(s['split_entry_worker_rows'])==s['split_entry_rows']
        assert b['publication']['row_reads']-a['publication']['row_reads']==s['duplicate_current_row_reads']
        before,after=[r['publication']['parallel'] for r in reports]
        keys=('batches','tables','rows','pool_calls','inline_rows','row_reads','task_capacity_bytes',
              'prepare_seconds','execute_seconds','restore_seconds','entry_order_headers')
        result['workloads'][case]=dict(
            unchanged_entry_work={k:b['entry_schedule']['stats'][k] for k in entry_keys},
            unchanged_sieve_work=True,
            publication={lane:{k:r[k] for k in keys} for lane,r in zip(('control','candidate'),(before,after))},
            split={k:s[k] for k in ('split_entry_tasks','split_entry_rows','split_entry_row_reads',
                'duplicate_current_row_reads','single_table_split_batches','indexes_released_before_entries',
                'split_entry_worker_rows','split_entry_worker_seconds','entry_order_capacity_bytes')})
    output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result['workloads'],indent=2))


if __name__=='__main__':
    if not __debug__:
        raise SystemExit('Run without Python -O')
    run(*(Path(arg).resolve() for arg in sys.argv[1:]))
