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
from reference_cell_closure import scheduled,seeds,facts_from_cells
from audit_snapshot_queries import device

RULES=[534,535,536,537]


def main():
    p=argparse.ArgumentParser();p.add_argument('trace',type=Path);p.add_argument('model',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--family',type=Path);p.add_argument('--corpus-manifest',type=Path);p.add_argument('--capture',type=Path);p.add_argument('--capacity',type=int,default=32);p.add_argument('--ticks',type=int,default=24);a=p.parse_args()
    raw=read_bytes(a.trace);trace=json.loads(raw);recipe=trace['recipe']
    capture_partition=None
    if a.capture is not None:
        if a.corpus_manifest is None:raise ValueError('capture requires corpus manifest')
        from device_match_capture import partition
        capture_partition=partition(trace,a.corpus_manifest)
    if not all(trace.get(k) is True for k in ('strict_run_graphs_equal','strict_audit_reference_equal','run_control_counts_equal')):raise ValueError('capture audit missing')
    from cell_family_plan import family,withhold
    if a.family:
        config=json.loads(a.family.read_text());rules,stages,control_plan=family(recipe,config)
        boundaries=[b['graph'] for b in trace.get('boundaries',[]) if b['ordinal']==config['snapshot_run']]
        if len(boundaries)!=1:raise ValueError('required Run snapshot absent or duplicate')
        source_snapshot=boundaries[0]
    else:
        rules=RULES;stages=['type-analysis'];control_plan=dict(saturate=dict(run='type-analysis'))
        config=dict(remove_tables=['PureType','PureTypeList']);source_snapshot=trace['final']
    snapshot,removed_rows=withhold(source_snapshot,recipe,config)
    local,state,ids,rows=prepare_family(recipe,snapshot,rules,a.capacity,True)
    plans=[(stages.index(local['rules'][rid]['metadata']['source_set']),compile_transition(local,rid)) for rid in range(len(rules))]
    plans,catalog,atoms=compile_catalog(local,plans,state['slots'].shape[1]);packed=initialize(pack(state),atoms)
    with np.load(a.model) as saved:
        if str(saved['encoding'])!='class-history-neighborhood-input' or int(saved['channels'])!=4 or bool(saved.get('source_neighborhood',False)) or bool(saved.get('source_relations',False)):raise ValueError('model interface mismatch')
        model=device({k:saved[k] for k in ('w','coef')})
    schedule,meta=compile_schedule(control_plan,stages)
    cp=device(compile_completion(local,state['slots'].shape[1]));dp=[(s,device(p)) for s,p in plans];ds=device(schedule)
    control=dict(control=initial(ds,meta['repeat_slots'],mx),open_run=mx.array(False),unreported_change=mx.array(False),failed_run=mx.array(False))
    next_id=mx.array(len(ids));current=device(packed)
    def query(s,b,m,stage,xp,**kwargs):return run_round(s,b,m,stage,xp,capacity=a.capacity,capture=a.capture is not None,**kwargs)
    def step(s,n,c):
        return run(s,dp,model,cp,ds,meta['repeat_slots'],mx.array([True]*len(stages)),n,mx.array(len(ids)+256),mx.array(a.capacity),mx.array(True),mx.array(True),1,mx,continuation=c,query_kernel=query,takeover_catalog=catalog,takeover_budget=8)
    compiled=mx.compile(step);logs=[];captures=[];start=time.monotonic()
    for _ in range(a.ticks):
        current,next_id,marks=compiled(current,next_id,control)
        logs.append({k:marks[k] for k in ('stage','run_done','run_changed','new_tokens','new_constructors','takeover_released','takeover_blocked')})
        if a.capture is not None:captures.append(marks['query_captures'])
        control={k:marks[k] for k in ('control','open_run','unreported_change','failed_run')}
    mx.eval(current,next_id,marks,logs,captures);gpu=time.monotonic()-start
    start=time.monotonic();final={k:np.array(v) for k,v in current.items()};log={k:np.concatenate([np.array(l[k]) for l in logs]) for k in logs[0]}
    expected,cpu_runs=scheduled(local['rules'][:len(rules)],rows,ids,control_plan)
    changes=[r['new_facts'] for r in cpu_runs];applications=[r['applications'] for r in cpu_runs]
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
    gpu_stages=[stages[i] for i in log['stage'][done]]
    result=dict(scope='real selected immutable Cell family on incomplete snapshot seeds; not full Eggcc runtime',trace_sha256=hashlib.sha256(raw).hexdigest(),model_sha256=hashlib.sha256(a.model.read_bytes()).hexdigest(),rules=rules,stages=stages,control=control_plan,snapshot_run=config.get('snapshot_run'),source_control_path=config.get('control_path'),family_config_sha256=hashlib.sha256(a.family.read_bytes()).hexdigest() if a.family else None,removed_rows=removed_rows,gpu_run_stages=gpu_stages,cpu_run_stages=[r['stage'] for r in cpu_runs],
        seed_rows=len(rows),capacity=a.capacity,ticks=a.ticks,finished=bool(marks['finished']),failed_run=bool(marks['failed_run']),
        generated_cells=int(log['new_tokens'].sum()),fresh_constructor_ids=len(fresh),released_rows=int(log['takeover_released'].sum()),blocked_takeovers=int(log['takeover_blocked'].sum()),
        gpu_run_new_facts=gpu_changes,gpu_run_new_cells=log['new_tokens'][done].tolist(),pending_cells=int(np.count_nonzero(final['present']&~final['settled'])),live_owners=int(final['owner_live'].sum()),logical_cells=int(final['present'].sum()),cpu_run_new_facts=changes,cpu_applications_per_run=applications,
        expected_facts=len(expected),actual_facts=len(actual),exact_closure=actual==expected,views_complete=view_complete,unresolved_facts=len(remaining),explained_allocations=explained,unique_fresh_terms=unique,problems=problems,
        gpu_compile_upload_execute_seconds=gpu,cpu_closure_and_check_seconds=time.monotonic()-start,
        passed=bool(marks['finished']) and not bool(marks['failed_run']) and actual==expected and view_complete and not remaining and explained and unique and not problems and gpu_changes==changes and gpu_stages==[r['stage'] for r in cpu_runs],
        limitations=['Original rule bodies and selected source control projection; omitted rules/stages are not covered', 'No captured future matches or intermediate device readbacks; fixed host launch budget with device control',
            'Exact GPU query/effect kernels establish completion; ridge accuracy and neural-like throughput remain unproved', 'Withheld facts in an exported snapshot; not original initialization or native Run equivalence'])
    if a.capture is not None:
        from device_match_capture import host,flatten,audit,floating_inputs
        from multi_entry_ridge import template,encode
        cpu_model={k:np.array(v) for k,v in model.items()};saved={};samples=[];targets=[];predictions=[];sample_rules=[];target_classes=[]
        capture_errors=[];checks=[];continued_samples=0;relocated_witnesses=0;numerical_max=0.;target_max=0.;capture_start=time.monotonic()
        for tick,batch in enumerate(captures):
            for inner,blocks in enumerate(batch):
                for block,c in enumerate(blocks):
                    c=host(c)
                    if not bool(c['recorded']):continue
                    check=audit(local,c);checks.append(check)
                    if not check['passed'] or not check['enumeration_complete']:capture_errors.append('invalid_match_capture')
                    if 'physical_owner' in c['witness']:
                        relocated_witnesses+=int(np.count_nonzero(c['bindings']['live'][:,None]&(c['witness']['physical_owner']!=c['bindings']['witness_rows'])))
                    saved.update(flatten(c,f'{tick}/{inner}/{block}/'))
                    features=floating_inputs(c,cpu_model,np);live=c['bindings']['live']
                    inferred=np.tanh(features@cpu_model['coef'])
                    if live.any():numerical_max=max(numerical_max,float(np.max(abs(inferred[live]-c['predicted_tokens'][live]))))
                    rid=int(c['rule']);rule=local['rules'][rid];roles,_=template(rule)
                    required=[i for i,s in enumerate(rule['slots']) if s['definition']=='query']
                    for lane in np.flatnonzero(c['accepted']):
                        continued_samples+=int(np.any(c['request']['edge_valid'][lane]&(c['source_rules'][lane]<len(rules))))
                        values={slot:known[int(c['bindings']['slots'][lane,slot])] for slot in required}
                        for op in rule['effects']:
                            if op['kind']=='copy':values[op['dst']]=values[op['arg']['slot']]
                            elif op['kind']=='construct':values[op['dst']]=expected[(op['call']['table'],tuple(values[arg['slot']] for arg in op['args']))]
                            else:raise ValueError('unsupported captured training target')
                        if any(rule['slots'][slot]['sort']['kind']!='eq' for slot in values):raise ValueError('Eq-only family target encoder')
                        target=encode([(slot,{},(rule['slots'][slot]['sort']['name'],value)) for slot,value in sorted(values.items())],roles,'class-balanced')
                        key=[rid]+[int(c['bindings']['slots'][lane,slot]) for slot in required]
                        key += [-1]*(final['keys'].shape[1]-len(key))
                        matching=np.flatnonzero(final['present']&np.all(final['keys']==np.array(key),axis=1))
                        if len(matching)!=1 or not final['settled'][matching[0]]:capture_errors.append('missing_completed_target');continue
                        target_max=max(target_max,float(np.max(abs(final['tokens'][matching[0]]-target))))
                        labels=np.full(state['slots'].shape[1],-1,np.int32);classes={}
                        for slot,value in sorted(values.items()):
                            key=(rule['slots'][slot]['sort']['name'],value);labels[slot]=classes.setdefault(key,len(classes))
                        target_classes.append(labels)
                        samples.append(features[lane]);targets.append(target);predictions.append(c['predicted_tokens'][lane]);sample_rules.append(rules[rid])
        if numerical_max>5e-6:capture_errors.append('floating_input_mismatch')
        if target_max>5e-6:capture_errors.append('independent_target_mismatch')
        if len(samples)!=result['generated_cells']:capture_errors.append('sample_admission_mismatch')
        payload=dict(target_eq_classes=np.array(target_classes,np.int32),features=np.array(samples,np.float32),targets=np.array(targets,np.float32),predicted_tokens=np.array(predictions,np.float32),rules=np.array(sample_rules,np.int32),**{'capture/'+k:v for k,v in saved.items()})
        result['capture']=dict(schema='device-joint-witness/v2',**capture_partition,samples=len(samples),continued_samples=continued_samples,relocated_witness_observations=relocated_witnesses,matched_snapshots=sum(c['checked'] for c in checks),query_calls=len(checks),
            errors=capture_errors,passed=not capture_errors,feature_reconstruction_max_abs=numerical_max,target_reconstruction_max_abs=target_max,
            logical_array_bytes=sum(v.nbytes for v in payload.values()),padded_capture_array_bytes=sum(v.nbytes for v in flatten(captures).values()),cpu_audit_and_prepare_seconds=time.monotonic()-capture_start,
            scope='actual GPU-selected joint witnesses and independent CPU completion targets; selected immutable family only')
        result['passed'] &= not capture_errors
        if result['passed']:
            a.capture.parent.mkdir(parents=True,exist_ok=True)
            np.savez_compressed(a.capture,**payload)
            result['capture']['artifact_sha256']=hashlib.sha256(a.capture.read_bytes()).hexdigest()
            a.capture.with_suffix('.json').write_text(json.dumps(dict(recipe=local,source_rules=rules,stages=stages,control=control_plan,snapshot_run=config.get('snapshot_run'),source_control_path=config.get('control_path'),family_config_sha256=hashlib.sha256(a.family.read_bytes()).hexdigest() if a.family else None,removed_rows=removed_rows,gpu_run_stages=gpu_stages,cpu_run_stages=[r['stage'] for r in cpu_runs],trace_sha256=result['trace_sha256'],model_sha256=result['model_sha256'],capture=result['capture']),indent=2)+'\n')
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
    if not result['passed']:raise SystemExit(1)

if __name__=='__main__':main()
