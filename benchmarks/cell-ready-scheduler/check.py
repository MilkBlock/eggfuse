#!/usr/bin/env python3
"""Conserved source semantics and actual ready-queue coverage; no timing claim."""
import hashlib
import json
from pathlib import Path
import sys

def read(p): return json.loads(p.read_text())
def sha(p):
    with p.open('rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()

def check(root, prior, output):
    result = {'scope': 'standalone Cell CPU runtime; not native egglog performance',
              'control_commit': '83acd095', 'control_runtime_commit': '877ff5d2',
              'runtime_sha256': sha(root/'runtime'), 'control_runtime_sha256': sha(prior/'runtime'),
              'workloads': {}}
    fields = ('ordinal','ruleset','path','iterations','epoch','logical_matches','executed_bindings','changed')
    effects = ('constructor_requests','constructor_reused','logical_facts_created',
               'function_updates','union_requests','unions','bindings')
    for case in ('sum','ray'):
        a,b = [read(p/case/'report.json') for p in (prior,root)]
        assert a['status'] == b['status'] == 'complete'
        assert a['program_sha256'] == b['program_sha256']
        state=sha(root/case/'state.json')
        assert state == sha(prior/case/'state.json'), (case,'final graph')
        assert [[r[k] for k in fields] for r in a['steps']] == [[r[k] for k in fields] for r in b['steps']], (case,'Runs')
        for key in effects: assert a['stats'][key] == b['stats'][key], (case,key)
        stats=b['cell_execution']['runtime']['stats']
        queue=stats['scheduler']; births=stats['births']
        assert b['cell_execution']['scheduler']['schema']=='cell-ready-batches/v1'
        assert births['slot_leases']==births['slot_reattachments']
        assert births['local_births']==births['committed_rows']
        assert b['stats']['rhs_suspend_holds']==b['stats']['rhs_suspend_releases']
        assert births['root_writes']==births['root_merges']==0
        # Worker participation is evidence of exercised dispatch, not utilization.
        assert sum(queue['worker_jobs'])==queue['jobs']
        ledger=read(root/f'{case}-work.json')
        result['workloads'][case] = {'program_sha256':b['program_sha256'],'state_sha256':state,
            'ordered_runs':len(b['steps']),'exact_final_state_and_ordered_run_summaries':True,
            'logical_effect_totals_equal':True, 'scheduler':queue, 'local_construction':births,
            'global_lookup_calls':[a['key_lookup_calls'],b['key_lookup_calls']],
            'runtime_slot_layout':b['cell_execution']['local_construction'],
            'compiled_execution_bytes':[a['cell_execution']['compiled_payload_bytes'],b['cell_execution']['compiled_payload_bytes']],
            'net_saved_uncalibrated_operations':ledger['net_saved_operations']}
    proof=read(root/'semantic-acceptance.json')
    assert proof['status']=='pass'
    assert proof['input_sha256']['cpu_values']==result['workloads']['sum']['state_sha256']
    result['native_sum_acceptance']={'status':'pass','sha256':sha(root/'semantic-acceptance.json')}
    output.write_text(json.dumps(result,indent=2)+'\n')
    print('source effects, ordered Runs and final states agree; queue costs and coverage recorded')

if __name__=='__main__':
    if not __debug__: raise SystemExit('run without Python -O')
    check(*map(Path,sys.argv[1:]))
