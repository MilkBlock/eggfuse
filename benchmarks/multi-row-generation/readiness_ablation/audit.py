"""Independent CPU audit of a completed device trace, including late/absent source lineage."""
from collections import Counter
import numpy as np
from data import oracle, KEYS, WAVES, VARIANTS

MODES=('barrier','barrier_min','local','raw','guarded','guarded_drain')
BOOL_KEYS=('parent_live','ready','runnable','proposal','fired','drained','early','published','computed','hidden','public','pending','sealed_absent','pending_open','withheld')


def checked_arrays(trace,batch):
    shapes={**{k:(batch,4,3,KEYS) for k in ('parent_live','parent_value','parent_first_tick','parent_version','receipt_count')},
            **{k:(batch,4,2,KEYS) for k in ('ready','runnable','proposal','fired','drained','early','published','computed','hidden','public','pending','sealed_absent','pending_open','withheld','first_fired_tick','first_publish_tick','first_early_tick')},
            'rows':(batch,4,2,KEYS,3),'public_rows':(batch,4,2,KEYS,3),'witness':(batch,4,2,KEYS,2,4),'input_fault':(batch,4)}
    checked={}
    for k,shape in shapes.items():
        value=np.asarray(trace[k]);
        if value.shape!=shape or value.dtype.kind not in 'biu':raise ValueError(f'{k}: expected discrete shape {shape}')
        if k in BOOL_KEYS or k=='input_fault':
            if not np.isin(value,[0,1]).all():raise ValueError(f'{k}: nonbinary flag')
            value=value.astype(bool)
        checked[k]=value
    return checked


def _event_counts(events):
    batch=len(events);per_wave=np.zeros((batch,4,3,KEYS),np.int32)
    for i in range(3):
        for k in range(KEYS):
            per_wave[:,:3,i,k]=((events[...,0]==i+1)&(events[...,1]==k)).sum(-1)
    return per_wave


def _lineage(t,g,frame,gold,counts):
    valid=np.zeros((2,KEYS),bool)
    counts['early_fires']+=int((frame['fired'][g,t]&~gold['desired_ready'][g,t]).sum())
    for c,key in zip(*np.nonzero(frame['fired'][g,t])):
        deps=(0,1) if c==0 else (2,);obs=frame['witness'][g,t,c,key]
        correct=True
        for n,producer in enumerate(deps):
            kind,got,value,wave=map(int,obs[n]);exists=gold['parent_live'][g,t,producer,key]
            if (obs[n]==-1).all():
                counts['absent_parent_witnesses']+=1;correct=False;continue
            if (kind,got)!=(producer+1,key):
                counts['wrong_parent_identity']+=1;correct=False
                if got!=key and exists and value==gold['parent_value'][g,t,producer,key]:counts['equal_value_wrong_key']+=1
            if not (1<=kind<=3 and 0<=got<KEYS and gold['parent_live'][g,t,kind-1,got]):
                counts['claimed_unpublished_parent']+=1;correct=False;continue
            if wave!=gold['parent_first_tick'][g,t,kind-1,got]:counts['wrong_publication_epoch']+=1;correct=False
            if value!=gold['parent_value'][g,t,kind-1,got]:counts['wrong_witness_value']+=1;correct=False
            if not exists:correct=False
        if c==1 and not (obs[1]==-1).all():counts['extra_parent_witnesses']+=1;correct=False
        # Match actual projected columns to the actual recorded (possibly invalid) read.
        projected=(int(obs[0,1]),int(obs[0,2]),int(obs[1,2]) if c==0 else -1)
        if tuple(frame['rows'][g,t,c,key])!=projected:counts['rhs_projection_mismatch']+=1;correct=False
        if gold['desired_ready'][g,t,c,key] and np.any(frame['rows'][g,t,c,key]!=gold['expected_rows'][g,t,c,key]):
            counts['wrong_ready_rhs']+=1;correct=False
        valid[c,key]=correct and gold['desired_ready'][g,t,c,key]
        if not valid[c,key]:counts['invalid_fired_witnesses']+=1
    return valid


def metrics(data,trace,mode):
    if mode not in MODES:raise ValueError(f'unknown scheduler mode {mode}')
    events,seal=data['events'],data['seal'];batch=len(events);frame=checked_arrays(trace,batch);gold=oracle(events,seal)
    if 'desired_ready' in data:np.testing.assert_array_equal(gold['desired_ready'],data['desired_ready'])
    actual=frame;fired=frame['fired'];pub=frame['published'];ready=gold['desired_ready'];produced=np.logical_or.accumulate(fired,axis=1)
    was=np.zeros_like(produced);was[:,1:]=produced[:,:-1];runnable=ready&~was;proposal=frame['proposal'];ticks=np.arange(4)[None,:,None,None]
    if mode=='local':prescribed=runnable
    elif mode in ('barrier','barrier_min'):prescribed=(ticks==3)&runnable
    elif mode=='raw':prescribed=proposal&~was
    else:prescribed=runnable&(proposal|((mode=='guarded_drain')&(ticks==3)))
    target_drains=runnable&~proposal&(ticks==3)&(mode=='guarded_drain')
    cumulative=np.cumsum(_event_counts(events),axis=1);observed_counts=actual['receipt_count'];actual_in=np.diff(observed_counts,axis=1,prepend=np.zeros_like(observed_counts[:,:1]))
    fresh=(gold['parent_first_tick']==np.arange(4)[None,:,None,None])&gold['parent_live'];previous_parent=np.zeros_like(actual['parent_live']);previous_parent[:,1:]=actual['parent_live'][:,:-1]
    writes=actual['parent_live']&~previous_parent;source_in=_event_counts(events)>0
    counted=lambda bits:int(np.count_nonzero(bits));graphs=[];run_arrays=[[] for _ in range(4)]
    for g in range(batch):
        c=Counter({k:0 for k in ('early_fires','absent_parent_witnesses','wrong_parent_identity','equal_value_wrong_key','claimed_unpublished_parent','wrong_publication_epoch','wrong_witness_value','extra_parent_witnesses','rhs_projection_mismatch','wrong_ready_rhs','invalid_fired_witnesses')})
        good=np.zeros((2,KEYS),bool);rhs_all=write_all=visible_all=True
        for t in range(4):
            new=_lineage(t,g,frame,gold,c);good=np.where(fired[g,t],new,good)
            live_equal=np.array_equal(actual['parent_live'][g,t],gold['parent_live'][g,t]) and np.array_equal(actual['parent_value'][g,t],gold['parent_value'][g,t]);
            parent_epoch_equal=np.array_equal(actual['parent_first_tick'][g,t],gold['parent_first_tick'][g,t]) and np.array_equal(actual['parent_version'][g,t],gold['parent_version'][g,t]);
            key_value_correct=actual['parent_value'][g,t]==gold['parent_value'][g,t]
            parent_rhs=np.array_equal(actual_in[g,t]>0,source_in[g,t]) and not ((actual_in[g,t]>0)&~key_value_correct).any()
            parent_ew=np.array_equal(writes[g,t],fresh[g,t]) and not (writes[g,t]&~key_value_correct).any()
            clients=gold['expected_public'][g,t];source_rows=np.where(clients[...,None],gold['expected_rows'][g,t],-1)
            correct_rows=(actual['public_rows'][g,t]==source_rows).all(-1)
            consumer_ew=np.array_equal(pub[g,t],clients) and bool(correct_rows[pub[g,t]].all())
            retained_lineage=np.ones((2,KEYS),bool)
            for kind,key in zip(*np.nonzero(pub[g,t])):
                deps=(0,1) if kind==0 else (2,)
                for side,producer in enumerate(deps):
                    if not gold['parent_live'][g,t,producer,key]:retained_lineage[kind,key]=False;continue
                    want=(producer+1,key,gold['parent_value'][g,t,producer,key],gold['parent_first_tick'][g,t,producer,key])
                    if tuple(actual['witness'][g,t,kind,key,side])!=want:retained_lineage[kind,key]=False
                if kind==1 and not (actual['witness'][g,t,kind,key,1]==-1).all():retained_lineage[kind,key]=False
            consumer_rhs=np.array_equal(pub[g,t],clients) and bool(good[pub[g,t]].all()) and bool(retained_lineage.all())
            consumer_visible=np.array_equal(actual['public'][g,t],clients) and bool(correct_rows.all())
            rr=dict(rhs_inputs_exact=bool(parent_rhs and consumer_rhs),effective_writes_exact=bool(parent_ew and consumer_ew),
                    visible_graph_exact=bool(live_equal and consumer_visible),receipt_epochs_exact=bool(parent_epoch_equal),private_rhs_evaluations=counted(fired[g,t]),private_valid_rhs_evaluations=counted(new),
                    private_still_hidden=counted(actual['hidden'][g,t]),withheld_runnable=counted(actual['withheld'][g,t]),
                    source_rhs_counts=gold['source_rhs_count'][g,t].tolist(),source_write_counts=gold['effective_write_count'][g,t].tolist(),
                    observed_rhs_counts=[*(actual_in[g,t]>0).sum(-1).astype(int).tolist(),*pub[g,t].sum(-1).astype(int).tolist()],
                    observed_write_counts=[*writes[g,t].sum(-1).astype(int).tolist(),*pub[g,t].sum(-1).astype(int).tolist()])
            rhs_all &= rr['rhs_inputs_exact'];write_all &= rr['effective_writes_exact'];visible_all &= rr['visible_graph_exact'];run_arrays[t].append(rr)
        correct_final=gold['expected_public'][g,-1];pending_expected=gold['pending_open'][g];seal_expected=gold['sealed_absent'][g]
        actual_first=np.where(produced[g,-1],fired[g].argmax(0),-1);early=fired[g]&~ready[g]
        actual_pub=np.logical_or.accumulate(pub[g],axis=0)
        cum_first=lambda pulses:np.where(np.logical_or.accumulate(pulses,axis=0),pulses.argmax(axis=0)[None],-1)
        consistent=(np.array_equal(frame['ready'][g],ready[g]) and np.array_equal(frame['runnable'][g],runnable[g])
                    and np.array_equal(frame['computed'][g],produced[g]) and np.array_equal(frame['public'][g],actual_pub)
                    and np.array_equal(frame['hidden'][g],produced[g]&~actual_pub) and np.array_equal(frame['early'][g],early)
                    and np.array_equal(frame['first_fired_tick'][g],cum_first(fired[g])) and np.array_equal(frame['first_publish_tick'][g],cum_first(pub[g]))
                    and np.array_equal(frame['first_early_tick'][g],cum_first(early))
                    and np.array_equal(frame['pending'][g],~(produced[g]|frame['sealed_absent'][g]))
                    and np.array_equal(frame['withheld'][g],frame['pending'][g]&ready[g])
                    and np.array_equal(frame['pending_open'][g],frame['pending'][g]&~ready[g])
                    and not frame['sealed_absent'][g,:3].any())
        stable=True
        for t in range(4):
            if np.any(frame['rows'][g,t,~produced[g,t]]!=-1) or np.any(frame['witness'][g,t,~produced[g,t]]!=-1):stable=False
            if t:
                for field in ('rows','witness'):
                    keep=was[g,t]&~fired[g,t];stable &= np.array_equal(frame[field][g,t][keep],frame[field][g,t-1][keep])
        keys=data['unrelated_key'];uk=int(keys[g]);fk=int(data['focal_key'][g]);
        idle=ready[g]&~produced[g];final_pub=frame['public'][g,-1];early_public=counted(frame['public'][g,:3]);never=correct_final & ~produced[g,-1];sealed_actual=frame['sealed_absent'][g,-1]
        c.update(dict(source_obligations=counted(correct_final),hidden_private_fires=counted(fired[g,:3]),
                 early_public_visible_slots=early_public,early_publication_events=counted(pub[g,:3]),duplicate_computations=int(np.maximum(fired[g].sum(0)-1,0).sum()),
                 duplicate_publications=int(np.maximum(pub[g].sum(0)-1,0).sum()),never_fired=counted(never),source_missing_public=counted(correct_final&~final_pub),
                 extra_final_public=counted(final_pub&~correct_final),final_public_wrong_rows=counted(final_pub&correct_final&~(frame['public_rows'][g,-1]==gold['expected_rows'][g,-1]).all(-1)),
                 source_pending_open=counted(pending_expected),source_sealed_absent=counted(seal_expected),pending_open_disagreements=counted(frame['pending_open'][g,-1]!=pending_expected),
                 sealed_absent_disagreements=counted(sealed_actual!=seal_expected),withheld_ready_at_end=counted(frame['withheld'][g,-1]),
                 blocked_early_proposals=counted(proposal[g]&~ready[g]&~was[g]) if mode in ('guarded','guarded_drain') else 0,
                 unguarded_proposals_before_ready=counted(proposal[g]&~ready[g]&~was[g]),missed_runnable_proposals=counted(runnable[g]&~proposal[g]) if mode in ('raw','guarded','guarded_drain') else 0,
                 unexpected_firing_decisions=counted(fired[g]!=prescribed[g]),drained_at_finish=counted(frame['drained'][g,-1]),drain_flag_disagreements=counted(frame['drained'][g]!=target_drains[g]),
                 ready_idle_obligation_ticks=counted(idle),unrelated_v_ready_idle_ticks=counted(idle[:,1,uk]),
                 receipt_transport_mismatches=counted(cumulative[g]!=observed_counts[g]),input_fault=int(frame['input_fault'][g].any()),
                 state_consistent=int(consistent),stable_retained_state=int(stable),source_rhs_exact=int(rhs_all),effective_writes_exact=int(write_all),
                 public_boundaries_exact=int(visible_all),final_graph_exact=int(run_arrays[-1][-1]['visible_graph_exact'])))
        delays=actual_first-gold['ready_tick'][g]
        valid_finished=good&correct_final
        for ci,rule in enumerate(('c','v')):
            valid=valid_finished[ci]
            c[rule+'_valid_private_results']=counted(valid)
            c[rule+'_valid_private_delay_ticks']=int(delays[ci][valid].sum())
            c[rule+'_early_attempts']=counted(early[:,ci]);c[rule+'_never_fired']=counted(never[ci]);c[rule+'_ready_wait_ticks']=counted(idle[:,ci])
            c[rule+'_published_valid_and_on_time']=counted(valid&final_pub[ci]&(actual['first_publish_tick'][g,-1,ci]==3))
        for label,ci,key in [('focal_c',0,fk),('unrelated_v',1,uk)]:
            expected=bool(correct_final[ci,key]);observed=bool(final_pub[ci,key]);legit=bool(good[ci,key] and retained_lineage[ci,key])
            correct_public=(observed==expected) and (not observed or (legit and np.array_equal(frame['public_rows'][g,-1,ci,key],gold['expected_rows'][g,-1,ci,key])))
            c[label+'_required']=int(expected);c[label+'_correct_required_public']=int(expected and correct_public)
            c[label+'_public_and_witness_exact']=int(correct_public);c[label+'_extra_public']=int(observed and not expected)
            c[label+'_withheld_ready_at_end']=int(expected and not observed)
        closed_ok=not(c['sealed_absent_disagreements'] or c['pending_open_disagreements'] or c['withheld_ready_at_end'])
        exact=bool(rhs_all and write_all and visible_all and c['invalid_fired_witnesses']==0 and closed_ok and consistent and stable
                   and c['receipt_transport_mismatches']==0 and c['unexpected_firing_decisions']==0 and c['drain_flag_disagreements']==0
                   and not(c['input_fault'] or c['duplicate_computations'] or c['duplicate_publications']) and all(rr[-1]['receipt_epochs_exact'] for rr in run_arrays))
        graphs.append(dict(**c,complete=exact,source_contract_exact=bool(rhs_all and write_all and visible_all),variant=str(VARIANTS[data['variant'][g]]),family=str(data['family'][g]),group_id=int(data['group_id'][g]),
                    focal_c_ready_tick=int(gold['ready_tick'][g,0,fk]),focal_c_fired_tick=int(actual_first[0,fk]),
                    unrelated_v_ready_tick=int(gold['ready_tick'][g,1,uk]),unrelated_v_fired_tick=int(actual_first[1,uk])))
    def summary(items):
        per=Counter()
        for row in items:
            for k,v in row.items():
                if k not in ('group_id','focal_c_ready_tick','focal_c_fired_tick','unrelated_v_ready_tick','unrelated_v_fired_tick') and isinstance(v,(bool,int,np.integer)):per[k]+=int(v)
        return dict(graphs=len(items),**per)
    per_run=[]
    for i,items in enumerate(run_arrays):
        counts={k:int(sum(x[k] for x in items)) for k in ('rhs_inputs_exact','effective_writes_exact','visible_graph_exact','receipt_epochs_exact','private_rhs_evaluations','private_valid_rhs_evaluations','private_still_hidden','withheld_runnable')}
        for name in ('source_rhs_counts','source_write_counts','observed_rhs_counts','observed_write_counts'):counts[name]=np.sum([x[name] for x in items],axis=0).tolist()
        per_run.append(dict(ordinal=i+1,**counts))
    return dict(graphs=batch,complete_graphs=sum(row['complete'] for row in graphs),final_graph_exact_graphs=sum(row['final_graph_exact'] for row in graphs),
                source_contract_exact_graphs=sum(row['source_contract_exact'] for row in graphs),per_run=per_run,totals=summary(graphs),
                by_variant={v:summary([r for r in graphs if r['variant']==v]) for v in sorted({r['variant'] for r in graphs})},
                by_family={v:summary([r for r in graphs if r['family']==v]) for v in sorted({r['family'] for r in graphs})},
                paired=counterfactuals(data,frame,graphs),per_graph=graphs)


def counterfactuals(d,trace,graphs):
    output=Counter();complete_groups=0
    for g in np.unique(d['group_id']):
        ix=np.flatnonzero(d['group_id']==g)
        if len(ix)!=4 or set(d['variant'][ix])!={0,1,2,3}:continue
        early,late,opened,sealed=sorted(map(int,ix),key=lambda i:int(d['variant'][i]));complete_groups+=1
        a,b,o,s=[graphs[i] for i in (early,late,opened,sealed)]
        output['c_follows_both_arrivals_at_earliest_tick']+=int(a['focal_c_fired_tick']==0 and b['focal_c_fired_tick']==2)
        output['c_waits_for_finish_on_both_valid_arrivals']+=int(a['focal_c_fired_tick']==b['focal_c_fired_tick']==3)
        output['c_timely_with_valid_public_witness_on_both_arrivals']+=int(a['focal_c_fired_tick']==0 and b['focal_c_fired_tick']==2 and a['focal_c_correct_required_public'] and b['focal_c_correct_required_public'])
        output['unrelated_v_correct_public_witness_all_four']+=int(all(graphs[i]['unrelated_v_correct_required_public'] for i in ix))
        output['c_suppressed_on_both_missing_variants']+=int(o['focal_c_fired_tick']==s['focal_c_fired_tick']==-1)
        keys=[int(d['unrelated_key'][i]) for i in (early,late,opened,sealed)];assert len(set(keys))==1;k=keys[0]
        same=all(np.array_equal(trace[tag][early,:,1,k],trace[tag][i,:,1,k]) for tag in ('fired','public','rows','public_rows','witness','first_fired_tick') for i in (late,opened,sealed))
        output['unchanged_unrelated_v_trajectory_groups']+=int(same)
        output['all_four_unrelated_v_fired_at_earliest_tick']+=int(all(graphs[i]['unrelated_v_fired_tick']==graphs[i]['unrelated_v_ready_tick'] for i in ix))
        # Causal-prefix checks are diagnostic, not a restriction on what the
        # learned model may do *after* a genuinely different event has arrived.
        same_prefix=all(np.array_equal(values[late,:2],values[opened,:2]) and np.array_equal(values[opened,:3],values[sealed,:3]) for values in trace.values())
        output['unchanged_observation_prefix_groups']+=int(same_prefix)
    return dict(groups=complete_groups,**output)


def _hash_values(data):
    import json
    from hashlib import sha256
    return sha256(json.dumps(data,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _file_sha(path):
    from hashlib import sha256
    return sha256(path.read_bytes()).hexdigest()


def rust_reference(d,cases,index,split):
    """Bind the independent source interpreter to each archived Rust Run."""
    from data import source_rows, TABLES, KINDS
    references=[];cache={}
    for i,(events,seal) in enumerate(zip(d['events'],d['seal'])):
        identifier=index[split][i];rust=cases[identifier];source=source_rows(events,seal)
        # Input contains seal for the surrounding stream protocol. The same
        # Rust relation program can serve an open/closed absent pair.
        event_rows=sorted({(w,KINDS[int(kind)-1],int(k),int(v)) for w,wave in enumerate(events) for kind,k,v in wave if kind})
        if _hash_values(event_rows)!=identifier:raise ValueError('wrong Rust replay case for raw graph')
        for match,run in zip(rust['runs'],source['runs']):
            if match['ordinal']!=run['ordinal']:raise ValueError('source Run order changed')
            for key,out in [('rhs','rhs_outputs_sha256'),('effective_writes','delta_sha256')]:
                emitted=sorted((tab,record) for tab in TABLES for record in run[key][tab])
                if _hash_values(emitted)!=match[out]:raise ValueError(f'{split}/{i}/{run["ordinal"]} source {key} mismatch')
            if _hash_values(run['visible'])!=match['visible_public_sha256']:raise ValueError('source graph differs from Rust snapshot')
        if _hash_values(source['finish_witnesses'])!=rust['finish_witnesses_sha256']:raise ValueError('source finish parents differ from Rust bindings')
        references.append(rust)
    return references


def rust_trace(trace,refs):
    """Hash actual GPU receipts, publication slots and source witness indices using the runtime schema."""
    from data import KINDS,TABLES
    counters=[Counter() for _ in range(4)];per_graph=[];witnesses_equal=0
    for g,case in enumerate(refs):
        before={k:set() for k in TABLES};parent_count=np.zeros((3,KEYS),np.int32);witness={'C':{},'V':{}};ok=True
        for i,run in enumerate(case['runs']):
            visible={k:[] for k in TABLES};rhs=[];eager={k:[] for k in ('C','V')}
            delta_counts=trace['receipt_count'][g,i]-parent_count;parent_count=trace['receipt_count'][g,i]
            for p,kind in enumerate(KINDS):
                for k in range(KEYS):
                    row=(k,int(trace['parent_value'][g,i,p,k]))
                    if trace['parent_live'][g,i,p,k]:visible[kind].append(row)
                    if delta_counts[p,k]>0:rhs.append((kind,row))
            for c,name in enumerate(('C','V')):
                width=3 if c==0 else 2
                for k in range(KEYS):
                    if trace['ready'][g,i,c,k]:
                        parent=trace['parent_value'][g,i];eager[name].append((k,int(parent[0,k]),int(parent[1,k])) if c==0 else (k,int(parent[2,k])))
                    row=tuple(map(int,trace['public_rows'][g,i,c,k,:width]))
                    if trace['public'][g,i,c,k]:visible[name].append(row)
                    if trace['published'][g,i,c,k]:
                        rhs.append((name,row));witness[name][k]=[tuple(map(int,w)) for w in trace['witness'][g,i,c,k,:(2 if c==0 else 1)]]
            visible={name:sorted(v) for name,v in visible.items()};now={name:set(v) for name,v in visible.items()}
            delta=sorted((name,row) for name in TABLES for row in now[name]-before[name]);deleted=sum(len(before[name]-now[name]) for name in TABLES);before=now
            checks=dict(rhs_outputs=_hash_values(sorted(rhs))==run['rhs_outputs_sha256'],effective_deltas=_hash_values(delta)==run['delta_sha256'] and not deleted,
                        visible_snapshots=_hash_values(visible)==run['visible_public_sha256'],possible_keyed_bindings=_hash_values(eager)==run['ready_sha256'])
            counters[i].update({k:int(v) for k,v in checks.items()});ok &= all(checks.values())
        bindings_ok=_hash_values(witness)==case['finish_witnesses_sha256'];witnesses_equal+=int(bindings_ok);per_graph.append(bool(ok and bindings_ok))
    return dict(graphs=len(refs),per_run=[dict(ordinal=i+1,**c) for i,c in enumerate(counters)],
                finish_witnesses_with_first_epoch_exact=witnesses_equal,all_cpu_run_hashes_and_finish_witnesses_exact=sum(per_graph),complete_by_graph=per_graph)


def _mode(label,stored):
    if stored.get('mode') in MODES:return stored['mode']
    for mode in sorted(MODES,key=len,reverse=True):
        if label==mode or label.endswith('-'+mode):return mode
    raise ValueError(f'unknown scheduler for {label}')


def replay(root,rust_path=None):
    import json
    from pathlib import Path
    import sys
    from data import dataset
    result_file=root/'results.json';result=json.loads(result_file.read_text());compiler=Path(__file__).parent/'compiler'
    proof=json.loads((compiler/'panel-audit.json').read_text());rust_path=Path(rust_path or proof['full_evidence_path'])
    if _file_sha(rust_path)!=proof['full_evidence_sha256']:raise ValueError('Rust evidence changed')
    archive=json.loads(rust_path.read_text());cases={r['id']:r for r in archive['cases']}
    if proof['input_generator_sha256']!=_file_sha(Path(__file__).with_name('data.py')):raise ValueError('source generator changed')
    panels={};trace_hashes={}
    for split in ('iid','heldout'):
        d=dataset(split);panels[split]={};refs=rust_reference(d,cases,archive['graph_to_source'],split)
        for label,stored in result['panels'][split].items():
            mode=_mode(label,stored);p=root/'traces'/f'{split}--{label}.npz';trace_hashes[p.name]=_file_sha(p)
            if 'trace_sha256' in result and p.name in result['trace_sha256'] and trace_hashes[p.name]!=result['trace_sha256'][p.name]:raise ValueError('saved trace checksum mismatch')
            with np.load(p,allow_pickle=False) as z:
                trace=checked_arrays(z,len(d['events']));r=metrics(d,trace,mode);native=rust_trace(trace,refs)
            for key in ('complete_graphs','source_contract_exact_graphs','final_graph_exact_graphs','per_run','paired','totals','by_family','by_variant'):
                if key in stored and r[key]!=stored[key]:raise ValueError(f'{split}/{label}/{key} differs')
            expected=stored.get('complete_by_graph')
            if expected is None:raise ValueError('missing original per-graph verdicts')
            if [int(x['complete']) for x in r['per_graph']]!=list(expected):raise ValueError('per-graph verdict mismatch')
            if mode in ('barrier','barrier_min','local','guarded_drain') and (r['complete_graphs']!=len(refs) or native['all_cpu_run_hashes_and_finish_witnesses_exact']!=len(refs)):
                raise ValueError(f'{split}/{label}: exact scheduler failed')
            panels[split][label]=dict(graphs=len(refs),mode=mode,complete=r['complete_graphs'],source_ordinal_hashes=native,
                                      paired=r['paired'],totals=r['totals'],complete_by_graph=expected)
            print(split,label,r['complete_graphs'],native['all_cpu_run_hashes_and_finish_witnesses_exact'],flush=True)
    if set(trace_hashes)!={p.name for p in (root/'traces').glob('*.npz')}:raise ValueError('not all traces covered')
    if 'torch' in sys.modules or 'mlx.core' in sys.modules:raise RuntimeError('source replay imported a neural runtime')
    return dict(schema='eggfuse.readiness.independent-replay/v1',results_sha256=_file_sha(result_file),audit_sha256=_file_sha(Path(__file__)),
                rust_evidence_sha256=_file_sha(rust_path),rust_distinct_sources=len(cases),trace_sha256=trace_hashes,panels=panels)


if __name__=='__main__':
    import argparse,json
    from pathlib import Path
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);parser.add_argument('--rust-evidence',type=Path);parser.add_argument('--output',type=Path)
    args=parser.parse_args();r=replay(args.root,args.rust_evidence);out=args.output or args.root/'cpu-replay.json'
    tmp=out.with_suffix('.tmp');tmp.write_text(json.dumps(r,separators=(',',':'))+'\n');tmp.replace(out)
    print('CPU replay checked',len(r['trace_sha256']),'saved trajectories against Rust source and independent temporal audit')
