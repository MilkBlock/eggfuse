"""Post-run CPU audit for gate policies over two logical rows and four rounds."""
from collections import defaultdict
from pathlib import Path
import sys

import numpy as np

BASE=Path(__file__).resolve().parents[1]
sys.path.append(str(BASE))
from eclass_ablation.data import audit as source_audit, paired_controls
from eclass_ablation.data.check import discrete
from width_ablation.audit import DUPLICATE_BINS, duplicate_profile, _origin_switches

ROWS=2
LENGTH=4
SLOTS=ROWS*LENGTH


def gate_bits(gates, first, second):
    """Normalize [batch, Run, row, round] or two stage-wise row-major arrays."""
    batch=len(first['active'])
    if gates is None:
        gates=(first['gate_open'],second['gate_open'])
    if isinstance(gates,(tuple,list)) and len(gates)==2:
        items=[]
        for raw in gates:
            x=np.asarray(raw)
            if x.shape not in ((batch,SLOTS),(batch,ROWS,LENGTH)):
                raise ValueError('each stage gate requires [B,8] or [B,2,4]')
            items.append(x.reshape(batch,ROWS,LENGTH))
        raw=np.stack(items,axis=1)
    else:
        raw=np.asarray(gates)
        if raw.shape==(batch,2,SLOTS):raw=raw.reshape(batch,2,ROWS,LENGTH)
    if raw.shape!=(batch,2,ROWS,LENGTH) or raw.dtype.kind not in 'biuf' or not np.isin(raw,[0,1]).all():
        raise ValueError('expected actual binary gate decisions [B,Run,row,round]')
    bits=raw.astype(bool)
    for stage,opened in zip((first,second),bits.transpose(1,0,2,3)):
        closed=~opened.reshape(batch,SLOTS)
        for k in ('active','pointers','rows','hidden','left_logits','right_logits','active_logits'):
            if k in stage:
                x=np.asarray(stage[k]);
                if x.shape[:2]!=(batch,SLOTS) or np.any(x[closed]!=0):
                    raise ValueError(f'closed slots must have zero {k}')
        if 'gate_open' in stage:
            np.testing.assert_array_equal(np.asarray(stage['gate_open']).reshape(batch,SLOTS),~closed)
    return bits


def verify_token(d,first,second,token,gates):
    """Check the real retained token, including zero address and history on closed slots."""
    bits=gate_bits(gates,first,second);batch=len(d['a']);f,s=bits.reshape(batch,2,SLOTS).transpose(1,0,2)
    token=np.asarray(token)
    if token.shape!=(batch,SLOTS,56) or not np.isfinite(token).all() or np.any(token[~f]!=0):
        raise ValueError('invalid retained Pair token or nonzero closed payload')
    g=np.arange(batch)[:,None]
    li,ri=np.asarray(first['pointers']).transpose(2,0,1);pi,qi=np.asarray(second['pointers']).transpose(2,0,1)
    for ids,mask,bound in ((li,f,d['a'].shape[1]),(ri,f,d['b'].shape[1]),(pi,s,SLOTS),(qi,s,d['requests'].shape[1])):
        if (ids[mask]<0).any() or (ids[mask]>=bound).any():raise ValueError('open pointer outside physical source range')
    for start,width,ids in ((32,2,first['active']),(34,8,li),(42,8,ri)):
        np.testing.assert_array_equal(token[...,start:start+width][f],np.eye(width)[np.asarray(ids)[f]])
    expect=np.concatenate((d['a'][g,li],d['b'][g,ri,1,None]),-1)
    np.testing.assert_array_equal(first['rows'][f],expect[f]);np.testing.assert_array_equal(token[...,50:55],first['rows'])
    np.testing.assert_array_equal(token[...,55][f],d['a_port'][g,li][f]);parent=token[g,pi,50:55]
    finish=np.concatenate((parent[...,:2],d['requests'][g,qi,4,None],parent[...,3:]),-1)
    np.testing.assert_array_equal(second['rows'][s],finish[s])


def _witnesses(d,g,first,second,legality):
    a,b,req=(d[k][g] for k in ('a','b','requests'))
    expected1={(i,j):tuple(map(int,[*x,y[1]])) for i,x in enumerate(a) for j,y in enumerate(b) if x[0]==y[0]}
    expected2={(*key,ri):(row[0],row[1],int(r[4]),row[3],row[4]) for key,row in expected1.items()
               for ri,r in enumerate(req) if legality[ri] and row[:2]==tuple(r[2:4])}
    def at(stage):return {k:stage[k][g] for k in ('active','pointers','rows')}
    slots={};legal1=[];correct1=[]
    for slot,key,row in discrete(at(first)):
        if key not in expected1:continue
        legal1.append((slot,key));ok=row==expected1[key];slots[slot]=(key,ok)
        if ok:correct1.append((slot,key))
    good_parents={key for _,key in correct1};ready2={key for key in expected2 if key[:2] in good_parents}
    legal2=[];correct2=[]
    for slot,(pi,ri),row in discrete(at(second)):
        if pi not in slots:continue
        parent,ok=slots[pi];key=(*parent,ri)
        if key not in expected2:continue
        legal2.append((slot,key))
        if ok and row==expected2[key]:correct2.append((slot,key))
    return [(set(expected1),set(expected1),legal1,correct1), (set(expected2),ready2,legal2,correct2)]


def _observe(bits,active,expected,ready,correct):
    # A correctly emitted binding counts as progress once. Reopening/closing a
    # row does not retire any source obligation and cannot repair a bad parent.
    active=np.asarray(active).reshape(ROWS,LENGTH).astype(bool)
    if np.any(active&~bits):raise AssertionError('emission from a closed gate')
    prior=set();by_slot=dict(correct);rounds=[];was_open=np.zeros(ROWS,bool);ever_open=np.zeros(ROWS,bool)
    reopens=0;late_opens=0
    for t in range(LENGTH):
        open_now=bits[:,t];opened=int(open_now.sum());remaining=len(ready-prior)
        # Opening for the first time after initial closure differs from reopening
        # a lane that previously ran and was then closed.
        reopened=open_now & ~was_open & ever_open
        first_late=open_now & ~ever_open if t else np.zeros(ROWS,bool)
        new={by_slot[row*LENGTH+t] for row in range(ROWS) if row*LENGTH+t in by_slot}-prior
        if not new<=ready:raise AssertionError('progress claimed for unavailable source binding')
        event=dict(round=t,source_remaining=len(expected-prior),ready_remaining=remaining,open_rows=opened,
                   emitted=int(active[:,t].sum()),new_semantic_bindings=len(new),
                   all_closed_with_ready=int(opened==0 and remaining>0),
                   all_closed_with_only_unavailable=int(opened==0 and remaining==0 and len(expected-prior)>0),
                   all_closed_after_complete=int(opened==0 and not expected-prior),
                   foregone_current_capacity=max(0,min(ROWS,remaining)-opened),
                   reopened=int(reopened.sum()),first_open_after_initial_closure=int(first_late.sum()))
        rounds.append(event);prior.update(new);reopens+=event['reopened'];late_opens+=event['first_open_after_initial_closure']
        ever_open |= open_now;was_open=open_now
    open_total=int(bits.sum());emitted=int(active.sum())
    capacity=max(0,len(ready)-open_total)
    if capacity>len(ready-prior):raise AssertionError('capacity bound exceeds unfinished ready work')
    return dict(source_obligations=len(expected),ready_obligations=len(ready),unavailable_obligations=len(expected-ready),
                open_slots=open_total,closed_slots=SLOTS-open_total,emitted=emitted,open_nonemitting=open_total-emitted,
                reopens=reopens,first_open_after_initial_closure=late_opens,source_unfinished=len(expected-prior),
                ready_unfinished=len(ready-prior),ready_capacity_shortfall=capacity,
                all_closed_graph=int(open_total==0),closed_with_unfinished=int(open_total<SLOTS and bool(expected-prior)),
                per_round=rounds)


def _bucket(rows):
    return dict(graphs=len(rows),nonempty=sum(int(r['source_obligations']>0) for r in rows),
                complete=sum(int(r['complete']) for r in rows),nonempty_complete=sum(int(r['complete'] and r['source_obligations']>0) for r in rows),
                **{key:sum(int(r[key]) for r in rows) for key in ('source_obligations','ready_obligations','unavailable_obligations',
                    'open_slots','closed_slots','emitted','open_nonemitting','reopens','first_open_after_initial_closure','source_unfinished',
                    'ready_unfinished','ready_capacity_shortfall','all_closed_graph','closed_with_unfinished','missing','duplicates','illegal','wrong_parent')})


def _gate_summary(d,rows):
    by_source=defaultdict(list);by_ready=defaultdict(list);groups=defaultdict(list);bins=defaultdict(list)
    hist=np.zeros((LENGTH,ROWS+1),dtype=np.int64)
    for i,r in enumerate(rows):
        by_source[r['source_obligations']].append(r);by_ready[r['ready_obligations']].append(r);groups[int(d['group_id'][i])].append(r)
        for e in r['per_round']:
            hist[e['round'],e['open_rows']]+=1;bins[e['ready_remaining']].append(e)
    round_bins={}
    for n,events in sorted(bins.items()):
        counts=np.bincount([e['open_rows'] for e in events],minlength=3)
        round_bins[str(n)]=dict(rounds=len(events),open_rows_hist=counts.tolist(),
                               **{k:sum(e[k] for e in events) for k in ('emitted','new_semantic_bindings','reopened','foregone_current_capacity',
                                'all_closed_with_ready','all_closed_with_only_unavailable','all_closed_after_complete')})
    result=_bucket(rows)
    result.update(by_source_obligations={str(k):_bucket(v) for k,v in sorted(by_source.items())},
                  by_ready_obligations={str(k):_bucket(v) for k,v in sorted(by_ready.items())},
                  by_group={str(k):_bucket(v) for k,v in sorted(groups.items())},
                  by_round_ready_remaining=round_bins,open_rows_hist_by_round=hist.tolist(),per_graph=rows)
    if result['open_slots']!=int((hist @ np.arange(3)).sum()) or result['emitted']+result['open_nonemitting']!=result['open_slots']:
        raise AssertionError('gate counts do not conserve row slots')
    return result


def metrics(data, first, second, gates=None, relation_pred=None):
    """Audit full or sampled source panels. Count logical gates separately from execution.

    Returns the original run1/run2/per_graph audit, duplicate bins, and gate.run1
    and gate.run2 reports with graph, group, and round-entry readiness buckets.
    Gate counts alone do not certify how many Metal instructions executed.
    """
    bits=gate_bits(gates,first,second);result=source_audit(data,first,second);gate_rows=[[],[]]
    for g,legal in enumerate(result['request_legal']):
        both=_witnesses(data,g,first,second,legal)
        for stage,tag,frame,(expected,ready,bound,correct) in zip((0,1),('run1','run2'),(first,second),both):
            source=result[tag]['per_graph'][g];dups=duplicate_profile(bound,SLOTS,ROWS)
            if sum(dups[k] for k in DUPLICATE_BINS)!=source['duplicates']:raise ValueError('duplicate bins differ from source')
            if stage==1:
                uses=defaultdict(set)
                for _,(i,j,ri) in bound:uses[i,j].add(ri)
                dups['distinct_requests_reusing_a_parent']=sum(len(ids)-1 for ids in uses.values())
            for k,v in dups.items():source[k]=v;result[tag][k]=result[tag].get(k,0)+v
            row=_observe(bits[g,stage],frame['active'][g],expected,ready,correct)
            if row['source_unfinished']!=source['semantic_missing'] or row['source_obligations']!=source['obligations']:
                raise ValueError('outstanding work differs from source audit')
            if stage==1 and row['unavailable_obligations']!=source['unavailable_parent_obligations']:raise ValueError('producer readiness differs')
            row.update(complete=source['complete'],missing=source['missing'],duplicates=source['duplicates'],
                       illegal=source['illegal'],wrong_parent=source.get('wrong_parent',0))
            gate_rows[stage].append(row)
    result['gate']={name:_gate_summary(data,rows) for name,rows in zip(('run1','run2'),gate_rows)}
    result['paired_controls']=None
    groups=defaultdict(list)
    for i,group in enumerate(data['group_id']):groups[int(group)].append(i)
    usable={k:ix for k,ix in groups.items() if len({(data['state'][i],data['variant'][i]) for i in ix})==len(ix)}
    result['origin_switch']=_origin_switches(data,first,second,usable)
    result['complete_intervention_groups']=sum(len(ix)==8 for ix in usable.values())
    if relation_pred is not None:
        choices=np.asarray(relation_pred);wanted=data['requests'].shape[:2]
        if choices.shape==wanted+(2,):
            if not np.isfinite(choices).all():raise ValueError('nonfinite relation head')
            choices=choices.argmax(-1)
        if choices.shape!=wanted or choices.dtype.kind not in 'biu' or not np.isin(choices,[0,1]).all():raise ValueError('invalid relation decisions')
        complete=[ix for ix in usable.values() if len(ix)==8]
        if complete:
            ix=np.array([i for group in complete for i in group])
            def sub(raw):return {k:(v[ix] if isinstance(v,np.ndarray) else v) for k,v in raw.items()}
            result['paired_controls']=paired_controls(sub(data),sub(first),sub(second),choices[ix])
    return result


def timed_rates(report,samples_ms):
    """Time-normalized *complete nonempty* graphs at each observed readiness.

    The i-th duration must belong to the exact i-th single-graph device output
    audited in `report`. No inference delay is inferred from a gate/work count.
    """
    latency=np.asarray(samples_ms,dtype=np.float64);rows=report['gate']['run2']['per_graph']
    if latency.shape!=(len(rows),) or not np.isfinite(latency).all() or (latency<=0).any():
        raise ValueError('one positive synchronized latency per audited graph required')
    success=np.array([r['complete'] and r['source_obligations']>0 for r in rows],dtype=bool)
    def stats(mask):
        times=latency[mask];wins=int(success[mask].sum())
        return dict(graphs=len(times),complete_nonempty=wins,elapsed_ms=float(times.sum()),
                    median_ms=float(np.median(times)),complete_nonempty_per_second=1000*wins/float(times.sum()))
    output={'all':stats(np.ones(len(rows),bool))}
    for typ,field in [('source','source_obligations'),('ready','ready_obligations')]:
        values=np.array([r[field] for r in rows]);output[typ]={str(k):stats(values==k) for k in np.unique(values)}
    return output


def execution_metrics(first,second,backend,gates=None):
    """Check explicit device instrumentation. A gate bit does not count work by itself.

    `executed` is the instrumented scorer-body entry bit, not a claim about
    input setup, dispatch or downstream kernels. Keep instrumented runs outside timing.
    """
    if backend not in ('dense','metal_dense','metal_skip'):raise ValueError('unknown scorer instrumentation backend')
    bits=gate_bits(gates,first,second);result={}
    for stage,label,opened in zip((first,second),('run1','run2'),bits.transpose(1,0,2,3)):
        b=opened.reshape(len(opened),SLOTS)
        if 'executed' not in stage:raise ValueError('actual execution instrumentation required')
        x=np.asarray(stage['executed'])
        if x.shape!=b.shape or not np.isin(x,[0,1]).all():raise ValueError('invalid execution counters')
        np.testing.assert_array_equal(x,b if backend=='metal_skip' else np.ones_like(b))
        executed=x.astype(bool)
        item=dict(candidate_rows=int(x.size),logical_open_rows=int(b.sum()),executed_scorer_rows=int(x.sum()),
                  executed_on_closed_rows=int((executed&~b).sum()),skipped_scorer_rows=int((~executed).sum()))
        if 'work_checksum' in stage:
            energy=np.asarray(stage['work_checksum']);
            if energy.shape!=x.shape or not np.isfinite(energy).all() or (energy<0).any() or np.any(energy[~executed]!=0):
                raise ValueError('unexpected scorer work checksum for an inactive scorer')
            item['closed_executed_positive_checksum_rows']=int((~b & executed & (energy>0)).sum())
        result[label]=item
    return result


def paired_readiness(data,report):
    """Within each source group, does a larger actionable demand receive more row slots?

    Only the finish source state/event changes across the two observations.
    A comparison is descriptive of the saved policy, not a causal attribution
    of each end-to-end outcome to its gate count.
    """
    records=report['gate']['run2']['per_graph'];lookup={}
    for i,key in enumerate(zip(data['group_id'],data['state'],data['variant'])):
        if key in lookup:raise ValueError('paired readiness requires unique counterfactual states')
        lookup[key]=i
    result={}
    for label,before,after in [('pre_to_post',0,1),('nonmerge_to_post',2,1),('post_to_external',1,3)]:
        stats={}
        for g in np.unique(data['group_id']):
            for v in (0,1):
                i,j=lookup.get((g,before,v)),lookup.get((g,after,v))
                if i is None or j is None:continue
                if not np.array_equal(data['requests'][i],data['requests'][j]):raise ValueError('source requests changed across a phase pair')
                a,b=records[i],records[j];ds=b['source_obligations']-a['source_obligations'];dr=b['ready_obligations']-a['ready_obligations'];dg=b['open_slots']-a['open_slots']
                if ds<0 or dr<0:raise ValueError('source equality is expected to grow monotonically across this intervention')
                # A changing producer would confound this stratum. Full greedy
                # trace replay separately verifies a common producer prefix.
                kind='more_ready' if dr>0 else 'source_only_growth' if ds>0 else 'unchanged_demand'
                counts=stats.setdefault(kind,dict(pairs=0,more_open=0,same_open=0,less_open=0,
                    delta_source=0,delta_ready=0,delta_open=0,both_complete=0))
                counts['pairs']+=1;counts['more_open' if dg>0 else 'less_open' if dg<0 else 'same_open']+=1
                counts['delta_source']+=ds;counts['delta_ready']+=dr;counts['delta_open']+=dg
                counts['both_complete']+=int(a['complete'] and b['complete'])
        result[label]=stats
    return result
