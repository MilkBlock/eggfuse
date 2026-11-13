"""Real pre-Run snapshot -> GPU union saturation, with independent CPU oracle.

Selected immutable copy/union family only; no claim of full source coverage.
"""
import argparse,hashlib,json,time
from pathlib import Path
import numpy as np
import mlx.core as mx
from device_snapshot_import import prepare_family,eq_registry
from device_join_transition import compile_transition,run_round
from device_constructor_completion import compile_completion
from device_matched_takeover import compile_catalog,initialize
from device_slot_owners import pack
from device_scheduled_runtime import run
from device_schedule import compile_schedule,initial
from reference_union_family import Reference
from reference_cell_closure import facts_from_cells
from audit_snapshot_queries import device
from device_match_capture import host,audit,flatten,floating_inputs,partition
from multi_entry_ridge import template,encode


def main():
    p=argparse.ArgumentParser()
    for key in ('trace','model','output'):p.add_argument(key,type=Path)
    p.add_argument('--rule',type=int,required=True);p.add_argument('--snapshot-run',type=int,required=True)
    p.add_argument('--capacity',type=int,default=32);p.add_argument('--ticks',type=int,default=12)
    p.add_argument('--capture',type=Path);p.add_argument('--corpus-manifest',type=Path);a=p.parse_args()
    raw=a.trace.read_bytes();trace=json.loads(raw)
    if not all(trace.get(k) is True for k in ('strict_run_graphs_equal','strict_audit_reference_equal','run_control_counts_equal')):raise ValueError('unaudited source')
    snapshot=[b['graph'] for b in trace['boundaries'] if b['ordinal']==a.snapshot_run]
    if len(snapshot)!=1:raise ValueError('snapshot boundary')
    rule=trace['recipe']['rules'][a.rule]
    if any(o['kind'] not in ('copy','union') for o in rule['effects']):raise ValueError('unsupported union family effect')
    provenance=partition(trace,a.corpus_manifest) if a.capture else None
    local,state,ids,rows=prepare_family(trace['recipe'],snapshot[0],[a.rule],a.capacity)
    stage=rule['metadata']['source_set'];control_plan=dict(saturate=dict(run=stage))
    plans=[(0,compile_transition(local,0))];plans,catalog,atoms=compile_catalog(local,plans,state['slots'].shape[1])
    completion=compile_completion(local,state['slots'].shape[1],include_unions=True)
    if completion['marks']:raise ValueError(completion['marks'])
    registry=eq_registry(ids,completion['eq_sort_names'],0)
    current=device(initialize(pack(state),atoms));cp=device(completion);dp=device(plans);ctx=device(registry)
    with np.load(a.model) as f:
        if str(f['encoding'])!='class-history-neighborhood-input' or int(f['channels'])!=4 or bool(f.get('source_neighborhood',False)) or bool(f.get('source_relations',False)):raise ValueError('model interface')
        model=device({k:f[k] for k in ('w','coef')})
    schedule,meta=compile_schedule(control_plan,[stage]);ds=device(schedule)
    control=dict(control=initial(ds,meta['repeat_slots'],mx),open_run=mx.array(False),unreported_change=mx.array(False),failed_run=mx.array(False))
    settled=mx.array(True);next_id=mx.array(len(ids));logs=[];captures=[]
    def query(s,b,m,st,xp,**kw):return run_round(s,b,m,st,xp,capacity=a.capacity,capture=True,**kw)
    def step(s,n,c,e,ready):
        return run(s,dp,model,cp,ds,meta['repeat_slots'],mx.array([True]),n,mx.array(len(ids)),mx.array(a.capacity),mx.array(True),ready,1,mx,
            eq_context=e,eq_rounds=8,continuation=c,query_kernel=query,takeover_catalog=catalog,takeover_budget=8)
    compiled=mx.compile(step);started=time.monotonic()
    for _ in range(a.ticks):
        current,next_id,marks=compiled(current,next_id,control,ctx,settled)
        logs.append({k:marks[k] for k in ('run_done','new_tokens','new_equivalences','takeover_released')})
        captures.append(marks['query_captures']);ctx=marks['eq_context'];settled=marks['eq_settled']
        control={k:marks[k] for k in ('control','open_run','unreported_change','failed_run')}
    mx.eval(current,next_id,marks,logs,captures);gpu_seconds=time.monotonic()-started
    started=time.monotonic();ref=Reference(local,rows,ids);cpu_runs=ref.saturate([local['rules'][0]])
    final=host(current);roots=np.array(ctx['roots']);expected=np.array(ref.partition())
    observed,complete=facts_from_cells(local,final)
    actual={(table,tuple(int(roots[v]) for v in (*args,result))) for table,args,result in observed}
    log={k:np.concatenate([np.array(x[k]) for x in logs]) for k in logs[0]}
    # Count across every effect tick, not just the tick which completes a Run.
    per_run=[];pending=0
    for done,unions in zip(log['run_done'],log['new_equivalences']):
        pending+=int(unions)
        if done:per_run.append(pending);pending=0
    result=dict(scope='standalone real snapshot selected copy/union Cell family; not full Eggcc',rule=a.rule,snapshot_run=a.snapshot_run,
        trace_sha256=hashlib.sha256(raw).hexdigest(),model_sha256=hashlib.sha256(a.model.read_bytes()).hexdigest(),seed_rows=len(rows),
        generated_cells=int(log['new_tokens'].sum()),released_owner_rows=int(log['takeover_released'].sum()),
        gpu_run_new_equivalences=per_run,cpu_runs=cpu_runs,exact_partition=bool(np.array_equal(roots,expected)),
        exact_facts=actual==ref.normalized_facts(),views_complete=complete,finished=bool(marks['finished']),failed_run=bool(marks['failed_run']),
        gpu_compile_upload_execute_seconds=gpu_seconds,cpu_reference_seconds=time.monotonic()-started)
    result['passed']=result['finished'] and not result['failed_run'] and result['exact_partition'] and result['exact_facts'] and complete and per_run==[r['new_equivalences'] for r in cpu_runs] and int(next_id)==len(ids)
    # Selected-witness capture uses CPU partition labels, never GPU roots as truth.
    saved={};xs=[];targets=[];predictions=[];classes=[];errors=[];checks=[];numerical_max=0.;target_max=0.;continued=0;roles,_=template(local['rules'][0]);cpu_model=host(model)
    for tick,batch in enumerate(captures):
        for inner,blocks in enumerate(batch):
            for block,c in enumerate(blocks):
                c=host(c)
                if not bool(c['recorded']):continue
                checked=audit(local,c);checks.append(checked)
                if not checked['passed'] or not checked['enumeration_complete']:errors.append('invalid_witness')
                saved.update(flatten(c,f'{tick}/{inner}/{block}/'));x=floating_inputs(c,cpu_model,np)
                live=c['bindings']['live']
                if live.any():numerical_max=max(numerical_max,float(np.max(abs(np.tanh(x@cpu_model['coef'])[live]-c['predicted_tokens'][live]))))
                for lane in np.flatnonzero(c['accepted']):
                    vals={i:int(expected[int(c['bindings']['slots'][lane,i])]) for i,s in enumerate(rule['slots']) if s['definition']=='query'}
                    for op in rule['effects']:
                        if op['kind']=='copy':vals[op['dst']]=vals[op['arg']['slot']]
                    if any(rule['slots'][i]['sort']['kind']!='eq' for i in vals):raise ValueError('Eq-only training capture')
                    target=encode([(i,{},(rule['slots'][i]['sort']['name'],v)) for i,v in sorted(vals.items())],roles,'class-balanced')
                    labels=np.full(state['slots'].shape[1],-1,np.int32);groups={}
                    for i,v in sorted(vals.items()):labels[i]=groups.setdefault((rule['slots'][i]['sort']['name'],v),len(groups))
                    required=[i for i,s in enumerate(rule['slots']) if s['definition']=='query']
                    key=[0]+[int(c['bindings']['slots'][lane,i]) for i in required]
                    key += [-1]*(final['keys'].shape[1]-len(key))
                    found=np.flatnonzero(final['present']&np.all(final['keys']==np.array(key),axis=1))
                    if len(found)!=1 or not final['settled'][found[0]]:errors.append('missing_completed_cell')
                    else:target_max=max(target_max,float(np.max(abs(final['tokens'][found[0]]-target))))
                    continued+=int(np.any(c['request']['edge_valid'][lane]&(c['source_rules'][lane]==0)))
                    xs.append(x[lane]);targets.append(target);predictions.append(c['predicted_tokens'][lane]);classes.append(labels)
    if numerical_max>5e-6:errors.append('floating_input_mismatch')
    if target_max>5e-6:errors.append('cpu_target_mismatch')
    if len(xs)!=result['generated_cells']:errors.append('sample_count_mismatch')
    result.update(feature_reconstruction_max_abs=numerical_max,target_reconstruction_max_abs=target_max,continued_samples=continued)
    result['capture_errors']=errors;result['passed'] &= not errors
    result['limitations']=['Projected single source ruleset, not full original schedule','Exact union/congruence kernels authorize effects; ridge predictions remain proposals','Final CPU labels include all selected-family unions; no claim of per-application targets']
    if a.capture and result['passed']:
        payload=dict(features=np.array(xs,np.float32),targets=np.array(targets,np.float32),predicted_tokens=np.array(predictions,np.float32),target_eq_classes=np.array(classes,np.int32),rules=np.full(len(xs),a.rule,np.int32),**{'capture/'+k:v for k,v in saved.items()})
        np.savez_compressed(a.capture,**payload)
        result['capture']=dict(schema='device-joint-witness/v2',**provenance,samples=len(xs),passed=True,artifact_sha256=hashlib.sha256(a.capture.read_bytes()).hexdigest(),target_scope='selected-family saturation')
        a.capture.with_suffix('.json').write_text(json.dumps(dict(recipe=local,source_rules=[a.rule],model_sha256=result['model_sha256'],capture=result['capture']),indent=2)+'\n')
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
    if not result['passed']:raise SystemExit(1)

if __name__=='__main__':main()
