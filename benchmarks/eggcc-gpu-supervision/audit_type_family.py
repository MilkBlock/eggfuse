"""Real type-analysis Cell family: device-owned saturation and owner takeover."""
import argparse,hashlib,json,time
from pathlib import Path
import numpy as np
import mlx.core as mx
from collect_observed_corpus import read_bytes
from device_snapshot_import import prepare_family
from device_join_transition import compile_transition,run_round
from device_constructor_completion import compile_completion
from device_matched_takeover import compile_catalog,initialize
from device_slot_owners import pack,read
from device_scheduled_runtime import run
from device_schedule import compile_schedule,initial
from device_witness_views import compile_view,project
from reference_cell_closure import saturate,seeds,facts_from_cells
from audit_snapshot_queries import device

RULES=[534,535,536,537]


def main():
    p=argparse.ArgumentParser();p.add_argument('trace',type=Path);p.add_argument('model',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--capacity',type=int,default=32);p.add_argument('--ticks',type=int,default=24);a=p.parse_args()
    raw=read_bytes(a.trace);trace=json.loads(raw);recipe=trace['recipe']
    if not all(trace.get(k) is True for k in ('strict_run_graphs_equal','strict_audit_reference_equal','run_control_counts_equal')):raise ValueError('capture audit missing')
    if any(recipe['rules'][r]['metadata']['source_set']!='type-analysis' for r in RULES):raise ValueError('unexpected source ruleset')
    snapshot=dict(trace['final'],rows=[r for r in trace['final']['rows'] if r['table'] not in ('PureType','PureTypeList')])
    local,state,ids,rows=prepare_family(recipe,snapshot,RULES,a.capacity,True)
    plans=[(0,compile_transition(local,rid)) for rid in range(len(RULES))]
    plans,catalog,atoms=compile_catalog(local,plans,state['slots'].shape[1]);packed=initialize(pack(state),atoms)
    with np.load(a.model) as saved:
        if str(saved['encoding'])!='class-history-neighborhood-input' or int(saved['channels'])!=4 or bool(saved.get('source_neighborhood',False)) or bool(saved.get('source_relations',False)):raise ValueError('model interface mismatch')
        model=device({k:saved[k] for k in ('w','coef')})
    schedule,meta=compile_schedule(dict(saturate=dict(run='type-analysis')),['type-analysis'])
    cp=device(compile_completion(local,state['slots'].shape[1]));dp=[(s,device(p)) for s,p in plans];ds=device(schedule)
    control=dict(control=initial(ds,meta['repeat_slots'],mx),open_run=mx.array(False),unreported_change=mx.array(False),failed_run=mx.array(False))
    next_id=mx.array(len(ids));current=device(packed)
    def query(s,b,m,stage,xp,**kwargs):return run_round(s,b,m,stage,xp,capacity=a.capacity,**kwargs)
    def step(s,n,c):
        return run(s,dp,model,cp,ds,meta['repeat_slots'],mx.array([True]),n,mx.array(len(ids)+256),mx.array(a.capacity),mx.array(True),mx.array(True),1,mx,continuation=c,query_kernel=query,takeover_catalog=catalog,takeover_budget=8)
    compiled=mx.compile(step);logs=[];start=time.monotonic()
    for _ in range(a.ticks):
        current,next_id,marks=compiled(current,next_id,control)
        logs.append({k:marks[k] for k in ('run_done','run_changed','new_tokens','new_constructors','takeover_released','takeover_blocked')})
        control={k:marks[k] for k in ('control','open_run','unreported_change','failed_run')}
    mx.eval(current,next_id,marks,logs);gpu=time.monotonic()-start
    start=time.monotonic();final={k:np.array(v) for k,v in current.items()};log={k:np.concatenate([np.array(l[k]) for l in logs]) for k in logs[0]}
    expected,changes,applications=saturate(local['rules'][:len(RULES)],rows,ids)
    # Decode actual constructor views, anchored only by imported seed IDs.
    observed,decoded_complete=facts_from_cells(local,final);view_complete=decoded_complete
    used={q['call']['table'] for r in local['rules'] for q in r['query']}|{o['call']['table'] for r in local['rules'] for o in r['effects'] if o['kind']=='construct'}
    for tid,t in enumerate(local['tables']):
        if t['name'] not in used:continue
        v=project(final,compile_view(local,tid,len(t['schema'])-1),True,True,np,include_fields=True);view_complete &= bool(v['complete'])

    known={i:('seed',i) for i in range(len(ids))};seed_facts=seeds(rows,ids);problems=[];remaining=list(set(observed))
    for _ in range(len(remaining)+1):
        following=[];progress=False
        for table,args,result in remaining:
            if any(x not in known for x in args):following.append((table,args,result));continue
            key=(table,tuple(known[x] for x in args));term=seed_facts.get(key,('construct',*key))
            if key in seed_facts and ('seed',result)!=seed_facts[key]:problems.append('seed result identity changed')
            if result in known:
                if known[result]!=term and key not in seed_facts:problems.append('fresh identity aliases different terms')
                elif key in seed_facts and known[result]!=seed_facts[key]:problems.append('seed result identity changed')
            else:known[result]=term;progress=True
        remaining=following
        if not remaining or not progress:break
    actual={(t,tuple(known[x] for x in args)):known[result] for t,args,result in observed if result in known and all(x in known for x in args)}
    fresh=list(range(len(ids),int(next_id)));explained=all(i in known for i in fresh)
    unique=len({known[i] for i in fresh if i in known})==len(fresh)
    done=log['run_done'];gpu_changes=log['new_constructors'][done].tolist()
    result=dict(scope='real four-rule type-analysis family on incomplete snapshot seeds; not full Eggcc multi-stage runtime',trace_sha256=hashlib.sha256(raw).hexdigest(),model_sha256=hashlib.sha256(a.model.read_bytes()).hexdigest(),rules=RULES,
        seed_rows=len(rows),capacity=a.capacity,ticks=a.ticks,finished=bool(marks['finished']),failed_run=bool(marks['failed_run']),
        generated_cells=int(log['new_tokens'].sum()),fresh_constructor_ids=len(fresh),released_rows=int(log['takeover_released'].sum()),blocked_takeovers=int(log['takeover_blocked'].sum()),
        gpu_run_new_facts=gpu_changes,gpu_run_new_cells=log['new_tokens'][done].tolist(),pending_cells=int(np.count_nonzero(final['present']&~final['settled'])),live_owners=int(final['owner_live'].sum()),logical_cells=int(final['present'].sum()),cpu_run_new_facts=changes,cpu_applications_per_run=applications,
        expected_facts=len(expected),actual_facts=len(actual),exact_closure=actual==expected,views_complete=view_complete,unresolved_facts=len(remaining),explained_allocations=explained,unique_fresh_terms=unique,problems=problems,
        gpu_compile_upload_execute_seconds=gpu,cpu_closure_and_check_seconds=time.monotonic()-start,
        passed=bool(marks['finished']) and not bool(marks['failed_run']) and actual==expected and view_complete and not remaining and explained and unique and not problems and gpu_changes==changes,
        limitations=['Original rule bodies, one selected ruleset family; other type-analysis rules are not covered', 'No captured future matches or intermediate device readbacks; fixed host launch budget with device control',
            'Exact GPU query/effect kernels establish completion; ridge accuracy and neural-like throughput remain unproved', 'Modified final snapshot is not original program initialization; no native run-boundary proof'])
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
    if not result['passed']:raise SystemExit(1)

if __name__=='__main__':main()
