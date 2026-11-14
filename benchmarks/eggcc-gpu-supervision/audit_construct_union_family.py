"""GPU construct/set/union family with original, unlowered CPU semantics."""
import argparse,hashlib,json,time
from copy import deepcopy
from pathlib import Path
import numpy as np
import mlx.core as mx
from lower_constructor_sets import lower
from device_snapshot_import import prepare_family,eq_registry
from device_join_transition import compile_transition,run_round
from device_constructor_completion import compile_completion
from device_matched_takeover import compile_catalog,initialize
from device_slot_owners import pack
from device_schedule import compile_schedule,initial
from device_scheduled_runtime import run
from device_match_capture import host,audit,flatten
from reference_union_family import Reference,compare_graph
from reference_cell_closure import facts_from_cells
from audit_snapshot_queries import device


def main():
    p=argparse.ArgumentParser()
    for k in ('trace','model','output'):p.add_argument(k,type=Path)
    p.add_argument('--capture',type=Path)
    p.add_argument('--rules',default='283,293');p.add_argument('--snapshot-run',type=int,default=466)
    p.add_argument('--progress',action='store_true');p.add_argument('--predicted-source-feedback',action='store_true');p.add_argument('--experimental-boundary-model',action='store_true');p.add_argument('--boundary-context',action='store_true');p.add_argument('--flush-every',type=int,default=4);p.add_argument('--order-queries',action='store_true');p.add_argument('--capacity',type=int,default=128);p.add_argument('--ticks',type=int,default=24);a=p.parse_args()
    if a.predicted_source_feedback and not a.experimental_boundary_model:raise ValueError('feedback requires explicit experimental model')
    if a.flush_every<1 or a.ticks<1:raise ValueError('positive execution window required')
    raw=a.trace.read_bytes();trace=json.loads(raw);ids_rule=[int(x) for x in a.rules.split(',')]
    if not all(trace.get(k) is True for k in ('strict_run_graphs_equal','strict_audit_reference_equal','run_control_counts_equal')):raise ValueError('unaudited trace')
    original=dict(trace['recipe'],rules=[trace['recipe']['rules'][i] for i in ids_rule])
    stages={r['metadata']['source_set'] for r in original['rules']}
    if len(stages)!=1:raise ValueError('single source stage required')
    stage=next(iter(stages));lowered,sites=lower(original)
    boundary=[b['graph'] for b in trace['boundaries'] if b['ordinal']==a.snapshot_run]
    if len(boundary)!=1:raise ValueError('snapshot boundary')
    local,state,ids,rows=prepare_family(lowered,boundary[0],list(range(len(ids_rule))),a.capacity)
    blocks=[(0,compile_transition(local,r)) for r in range(len(ids_rule))]
    if a.order_queries:
        from collections import Counter
        from device_query_join import order_query
        counts=Counter(r['table'] for r in rows);table_rows={i:int(counts[t['name']]) for i,t in enumerate(local['tables'])}
        blocks=[(st,dict(p,query=order_query(p['query'],table_rows))) for st,p in blocks]
    if a.boundary_context:
        from device_boundary_context import compile_context
        blocks=[(st,dict(p,boundary_context=compile_context(local,p['query']['rule'],state['slots'].shape[1]))) for st,p in blocks]
    query_orders=[p['query'].get('order',list(range(len(p['query']['atoms'])))) for _,p in blocks]
    blocks,catalog,atoms=compile_catalog(local,blocks,state['slots'].shape[1]);current=device(initialize(pack(state),atoms))
    plan=compile_completion(local,state['slots'].shape[1],include_unions=True)
    if plan['marks']:raise ValueError(plan['marks'])
    if a.predicted_source_feedback:plan['retain_predicted_rules']=tuple(range(len(ids_rule)))
    reserve=a.capacity*sum(o['kind']=='construct' for r in lowered['rules'] for o in r['effects'])
    registry=eq_registry(ids,plan['eq_sort_names'],reserve);ctx=device(registry);cp=device(plan);dp=device(blocks)
    with np.load(a.model) as f:
        boundary_model=bool(f.get('boundary_context',False))
        if boundary_model and not (a.experimental_boundary_model and a.boundary_context):raise ValueError('boundary predictor requires explicit experimental model and context flags')
        if a.experimental_boundary_model and not boundary_model:raise ValueError('expected a boundary-calibrated model')
        if str(f['encoding'])!='class-history-neighborhood-input' or int(f['channels'])!=4 or bool(f.get('source_neighborhood',False)) or bool(f.get('source_relations',False)):raise ValueError('model interface')
        if 'family_semantics' in f:
            family=[{k:r[k] for k in ('slots','query','effects')} for r in original['rules']]
            if json.loads(str(f['family_semantics']))!=family:raise ValueError('calibrated model family mismatch')
        model=device({k:f[k] for k in ('w','coef')})
    schedule,meta=compile_schedule(dict(saturate=dict(run=stage)),[stage]);ds=device(schedule)
    control=dict(control=initial(ds,meta['repeat_slots'],mx),open_run=mx.array(False),unreported_change=mx.array(False),failed_run=mx.array(False))
    ready=mx.array(True);next_id=mx.array(len(ids));logs=[];captures=[];frames=[]
    def query(s,b,m,st,xp,**kw):return run_round(s,b,m,st,xp,capacity=a.capacity,capture=True,**kw)
    def step(s,n,c,e,r):return run(s,dp,model,cp,ds,meta['repeat_slots'],mx.array([True]),n,mx.array(len(ids)+reserve),mx.array(a.capacity),mx.array(True),r,1,mx,
        eq_context=e,eq_rounds=8,continuation=c,query_kernel=query,takeover_catalog=catalog,takeover_budget=8)
    compiled=mx.compile(step);started=time.monotonic()
    for tick_index in range(a.ticks):
        current,next_id,m=compiled(current,next_id,control,ctx,ready);ctx=m['eq_context'];ready=m['eq_settled']
        control={k:m[k] for k in ('control','open_run','unreported_change','failed_run')}
        frames.append(dict(state={k:v for k,v in current.items() if k in ('keys','present','visible','settled','effect_pc','slot_owner','owner_projection','owner_live','owner_epoch','owner_generation','owner_slots','owner_slot_roots','owner_slot_valid')},roots=ctx['roots'],next_id=next_id))
        logs.append({k:m[k] for k in ('run_done','run_changed','new_tokens','new_constructors','new_equivalences','takeover_released')});captures.append(m['query_captures'])
        if (tick_index+1)%a.flush_every==0:
            mx.eval(current,next_id,m,logs[-a.flush_every:],captures[-a.flush_every:],frames[-a.flush_every:])
            if a.progress:print(json.dumps(dict(event='execution_flush',tick=tick_index+1,budget=a.ticks,elapsed_seconds=time.monotonic()-started)),flush=True)
    mx.eval(current,next_id,m,logs,captures,frames);gpu_seconds=time.monotonic()-started
    started=time.monotonic();ref=Reference(original,rows,ids);cpu_frames=[];cpu_runs=ref.saturate(original['rules'],observe=lambda r,_:cpu_frames.append(deepcopy(r)))
    lowref=Reference(lowered,rows,ids);lowruns=lowref.saturate(lowered['rules'])
    lowfacts=[(t,v[:-1],v[-1]) for t,v in lowref.facts]
    lowering_check=compare_graph(ref,lowfacts,lowref.partition(),len(ids))
    final=host(current);observed,complete=facts_from_cells(local,final);roots=np.array(ctx['roots'])[:int(next_id)]
    check=compare_graph(ref,observed,roots,len(ids));log={k:np.concatenate([np.array(v[k]) for v in logs]) for k in logs[0]}
    checks=[];continued=0;matched=[];per_rule_matches=[]
    for batch in captures:
        for blocks in batch:
            count=0;recorded=False;counts=[]
            for c in blocks:
                c=host(c)
                if not bool(c['recorded']):continue
                recorded=True;checks.append(audit(local,c));count+=checks[-1]['checked'];counts.append(checks[-1]['checked'])
                continued+=int(np.count_nonzero(c['accepted']&np.any(c['request']['edge_valid']&(c['source_rules']<len(ids_rule)),axis=1)))
            if recorded:matched.append(count);per_rule_matches.append(counts)
    boundary_checks=[]
    for frame in [frames[i] for i,done in enumerate(log['run_done']) if done]:
        if len(boundary_checks)>=len(cpu_frames):break
        frame=host(frame);facts,covered=facts_from_cells(local,frame['state'])
        check_run=compare_graph(cpu_frames[len(boundary_checks)],facts,frame['roots'][:int(frame['next_id'])],len(ids))
        check_run['passed'] &= covered;boundary_checks.append(check_run)
    source_counts=[r['applications'] for r in cpu_runs]
    passed=bool(m['finished']) and not bool(m['failed_run']) and len(boundary_checks)==len(cpu_runs) and all(b['passed'] for b in boundary_checks) and check['passed'] and lowering_check['passed'] and complete and per_rule_matches==[r['per_rule_applications'] for r in cpu_runs] and matched==source_counts and len(cpu_runs)==int(log['run_done'].sum()) and all(c['passed'] and c['enumeration_complete'] for c in checks)
    result=dict(scope='real selected construct/union family on GPU; not full Eggcc',rules=ids_rule,snapshot_run=a.snapshot_run,stage=stage,
        trace_sha256=hashlib.sha256(raw).hexdigest(),model_sha256=hashlib.sha256(a.model.read_bytes()).hexdigest(),lowered_sets=sites,
        seed_rows=len(rows),experimental_boundary_model=boundary_model,source_tokens='predicted generated Cells, exact imported Cells' if a.predicted_source_feedback else 'exact completed states',boundary_context=a.boundary_context,query_order=query_orders,fixed_ticks=a.ticks,flush_every=a.flush_every,host_execution_flushes=a.ticks//a.flush_every,generated_cells=int(log['new_tokens'].sum()),fresh_ids=int(next_id)-len(ids),original_cpu_fresh_ids=len(ref.parent)-len(ids),lowered_cpu_fresh_ids=len(lowref.parent)-len(ids),released_owner_rows=int(log['takeover_released'].sum()),generated_source_consumers=continued,
        cpu_runs=cpu_runs,lowered_cpu_runs=lowruns,gpu_matches_per_run=matched,gpu_matches_per_rule=per_rule_matches,gpu_runs=int(log['run_done'].sum()),gpu_run_changes=log['run_changed'][log['run_done']].tolist(),
        graph_check=check,boundary_checks=boundary_checks,lowering_check=lowering_check,views_complete=complete,query_checks=checks,finished=bool(m['finished']),failed_run=bool(m['failed_run']),passed=passed,
        gpu_compile_upload_execute_seconds=gpu_seconds,cpu_reference_and_audit_seconds=time.monotonic()-started,
        limitations=['One projected source ruleset, omitted external rules/tables remain uncovered','Lowering adds temporary slots and potentially fresh IDs/unions','Exact kernels authorize completion; ridge quality for lowered templates is not established','No claim of identical intermediate allocation or native full-graph execution'])
    if a.capture and passed:
        payload={}
        for ti,batch in enumerate(captures):
            for inner,blocks in enumerate(batch):
                for block,c in enumerate(blocks):
                    c=host(c)
                    if bool(c['recorded']):payload.update(flatten(c,f'capture/{ti}/{inner}/{block}/'))
        np.savez_compressed(a.capture,**payload)
        result['capture']=dict(schema='device-composed-witness/v1',artifact_sha256=hashlib.sha256(a.capture.read_bytes()).hexdigest(),passed=True,target_labels_included=False,logical_array_bytes=sum(x.nbytes for x in payload.values()))
        a.capture.with_suffix('.json').write_text(json.dumps(dict(recipe=local,original_recipe=original,source_token_mode=result['source_tokens'],snapshot_run=a.snapshot_run,source_rules=ids_rule,model_sha256=result['model_sha256'],trace_sha256=result['trace_sha256'],capture=result['capture']),indent=2)+'\n')
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
    if not passed:raise SystemExit(1)

if __name__=='__main__':main()
