"""Bounded cumulative GPU sweeps, followed by independent CPU replay.

Host loops follow a fixed compiled rule order, never observed candidate values.
This diagnostic is one constructor ruleset, not the native multi-stage runtime.
"""
from copy import deepcopy
import time
import numpy as np
import mlx.core as mx
from audit_snapshot_queries import device
from device_slot_owners import shape
from device_neural_speculation import compile_frame
from device_neural_step import advance
from neural_device_candidates import compile_candidates
from neural_cell_samples import apply_instance
from neural_cell_chains import completed
from reference_cell_closure import facts_from_cells
from reference_union_family import compare_graph


def run(local,state,roots,next_id,frames,rules,model,head,sweeps,oracle,mapping,seed_count,table_capacities=None):
    width=shape(state)[1];eq_width=max(len(r['slots']) for r in rules)
    atoms=max(len(r['query']) for r in rules);fields=max(len(a['args']) for r in rules for a in r['query'])
    offset=len(local['rules'])-len(rules)
    plans=[(device(compile_candidates(local,r,atoms=atoms,fields=fields,compact_constants=True,table_capacities=table_capacities)),
            compile_frame(r,width,eq_width,local,True)) for r in rules]
    attention=mx.array(False);idle=mx.array(False);trace=[]
    for _ in range(sweeps):
        all_idle=mx.array(True)
        for ri,(query,frame) in enumerate(plans):
            state,roots,next_id,event=advance(state,roots,next_id,frames,query,frame,offset+ri,model,head,~attention&~idle,mx)
            all_idle=all_idle&event['no_novel_proposal'];attention=attention|event['needs_attention']
            # Synchronize bounded allocations; no tensor value is read by host.
            mx.eval(state,roots,next_id,event,attention,all_idle)
            trace.append((ri,event))
        idle=idle|all_idle
    mx.eval(state,roots,next_id,attention,idle)
    started=time.perf_counter();ref=deepcopy(oracle);identities=dict(mapping)
    errors=[];admitted=0;capacity=0;refresh=0;replayed=0
    reasons={k:0 for k in ('query_overflow','query_incomplete','dirty_input','nonfinite','invalid_keys','rejected_proposal','payload_invalid')}
    attention_events=[]
    for ri,event in trace:
        if bool(event["needs_attention"]):attention_events.append(dict(rule=ri,pools={a["call"]["table"]:int(n) for a,n in zip(rules[ri]["query"],np.array(event["pool_sizes"]))}))
        for k in reasons:reasons[k]+=bool(event[k])
        capacity+=bool(event['capacity']);refresh+=bool(event['token_refresh_required'])
        if not bool(event['admitted']):continue
        admitted+=1
        if errors:continue
        rule=rules[ri];inputs=[i for i,s in enumerate(rule['slots']) if s['definition']=='query']
        key=np.array(event['key'])[1:1+len(inputs)]
        if any(int(v) not in identities for v in key):errors.append('unknown_input_identity');continue
        bound={s:ref.root(identities[int(v)]) for s,v in zip(inputs,key)}
        if bound not in ref.matches(rule):errors.append('invalid_effect_entry');continue
        apply_instance(ref,rule,bound);values=completed(rule,bound,ref)
        for handle,value in zip(np.array(event['result_slots']),values):
            handle=int(handle);value=ref.root(value)
            if handle in identities and ref.root(identities[handle])!=value:errors.append('inconsistent_result_identity')
            else:identities[handle]=value
        replayed+=1
    facts,covered=facts_from_cells(local,{k:np.array(v) for k,v in state.items()})
    graph=compare_graph(ref,facts,np.array(roots)[:int(next_id)],seed_count) if not errors else dict(passed=False,errors=errors)
    fixedpoint=False
    if covered and graph['passed']:
        probe=deepcopy(ref)
        # One exhaustive original-ruleset Run is enough to refute a claimed
        # fixed point; labels do not enter GPU state or change the executed run.
        matches=[probe.matches(rule) for rule in rules]
        for rule,bindings in zip(rules,matches):
            for binding in bindings:apply_instance(probe,rule,binding)
        fixedpoint=probe.constructions==ref.constructions and probe.unions==ref.unions
    return dict(scope='one cumulative GPU state; host fixed-order sweeps, final CPU audit',
                pool_capacity_overrides=table_capacities or {},candidate_lanes_per_sweep=sum(int(np.prod(q['capacities'])) for q,f in plans),
                sweeps=sweeps,scheduled_steps=len(trace),admitted=admitted,replayed=replayed,
                graph=graph,facts_decoded=covered,cpu_fixedpoint=fixedpoint,device_no_novel=bool(idle),
                needs_attention=bool(attention),attention_reasons=reasons,attention_events=attention_events,capacity_steps=capacity,refresh_steps=refresh,
                cpu_audit_seconds=time.perf_counter()-started,intermediate_host_value_reads=False,
                status='pass' if covered and graph['passed'] and fixedpoint and bool(idle) and not bool(attention) else 'difference')
