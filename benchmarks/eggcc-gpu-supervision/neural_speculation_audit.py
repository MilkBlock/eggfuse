"""CPU audit/correction of isolated neural Cell mutations and downstream queries."""
from copy import deepcopy
import time
import numpy as np
import mlx.core as mx
from device_neural_speculation import compile_frame,frame_payload,install,resolve
from device_slot_owners import shape
from neural_cell_samples import apply_instance
from neural_cell_chains import completed
from neural_device_candidates import compile_candidates,candidates
from reference_cell_closure import facts_from_cells
from reference_union_family import compare_graph
from audit_snapshot_queries import device


def audit(state,local,frames,rule,rid,batch,index,token,scores,model,oracle,key,mapping,base_roots,fresh_base,seed_count,eq_width,query_atoms=2,query_fields=5,reuse_witnesses=False,follow_rules=None,eq_head=None):
    width=shape(state)[1];plan=compile_frame(rule,width,eq_width,local,reuse_witnesses)
    payload,roots,ready=frame_payload(state,plan,batch,index,scores,mx.array(fresh_base),base_roots,mx)
    predicted,marks=install(state,payload,roots,batch,index,token,rid,plan['inputs'],ready,mx)
    mx.eval(predicted,roots,marks)
    if not bool(marks['accepted'][0]):raise ValueError('speculative frame was not admitted')
    # Query the proposed state before computing any exact completion labels.
    qp=compile_candidates(local,rule,atoms=query_atoms,fields=query_fields,compact_constants=True)
    downstream=candidates(predicted,frames,device(qp),mx.array(True),mx.array(True),mx)
    logits,_=model.transition(downstream['tokens'],downstream['edges'],downstream['mask'],downstream['request'],downstream['relations']);mx.eval(logits,downstream)
    round_outputs=None
    if follow_rules is not None:
        from neural_follow_round import evaluate
        round_outputs=evaluate(local,predicted,frames,follow_rules,model,eq_head,query_atoms,query_fields)
    started=time.perf_counter();ref=deepcopy(oracle);bound=dict(key);apply_instance(ref,rule,bound)
    values=completed(rule,bound,ref)
    from neural_eq_readout import targets,metrics
    label=targets(rule,values,ref,eq_width)
    local_eq_ok=metrics(np.array(scores)[None,:],label["eq_target"][None,:],label["eq_mask"][None,:],eq_width)["closed_exact_states"]==1
    raw=np.array(payload['slots'][0]);valid=np.array(payload['slot_valid'][0]);base=np.array(base_roots)
    # Canonicalize both old handles and newly allocated semantic output handles
    # through the independent CPU result, including external constructor reuse.
    wanted={i:ref.root(mapping[int(base[i])]) for i in range(fresh_base)}
    for slot,value in enumerate(values):wanted[int(raw[slot])]=ref.root(value)
    representative={}
    for handle,value in sorted(wanted.items()):representative.setdefault(value,handle)
    correct_roots=np.full(len(base),representative[wanted[0]],np.int32)
    for handle,value in wanted.items():correct_roots[handle]=representative[value]
    actual_facts,covered=facts_from_cells(local,{k:np.array(v) for k,v in predicted.items()})
    check=compare_graph(ref,actual_facts,np.array(roots)[:fresh_base+width],seed_count)
    passed=covered and check['passed']
    # Read predicted query keys in the correct semantic vocabulary. Rejected
    # merges and missed merges can both change which matches are emitted.
    accepted=np.array(downstream['live']&downstream['constraints_satisfied'])&(np.array(logits)>=0)
    expected={tuple(sorted(b.items())) for b in ref.matches(rule)};observed=set();unknown=0
    for row in np.flatnonzero(accepted):
        result=[]
        for slot,value in zip(qp['inputs'],np.array(downstream['binding_roots'][row])):
            if int(value) not in wanted:unknown+=1;break
            result.append((slot,wanted[int(value)]))
        else:observed.add(tuple(result))
    round_counts={}
    if round_outputs is not None:
        from neural_follow_round import audit as audit_round
        new_rows=np.flatnonzero(np.array(predicted['present']&~state['present']))
        round_counts=audit_round(round_outputs,follow_rules,ref,wanted,eq_width,new_rows)
    cpu_seconds=time.perf_counter()-started;correction_started=time.perf_counter()
    if passed:
        corrected=predicted;correction_pass=True;refresh=bool(marks['token_refresh_required'])
    else:
        fix=dict(payload,slot_roots=mx.array(correct_roots[np.clip(raw,0,len(correct_roots)-1)])[None,:])
        corrected,cm=install(state,fix,mx.array(correct_roots),batch,index,token,rid,plan['inputs'],mx.array(True),mx,dirty=True)
        mx.eval(corrected,cm)
        if not bool(cm['accepted'][0]):raise ValueError('corrected frame was not admitted')
        facts,coverage=facts_from_cells(local,{k:np.array(v) for k,v in corrected.items()})
        correction_pass=coverage and compare_graph(ref,facts,correct_roots[:fresh_base+width],seed_count)['passed']
        refresh=bool(cm['token_refresh_required'])
    resolved,verdict=resolve(predicted,predicted,corrected,mx.array(passed),mx.array(1),mx.array(1),mx);mx.eval(resolved,verdict)
    if not correction_pass:raise AssertionError('CPU correction did not restore exact graph')
    novel=(ref.constructions>oracle.constructions) or (ref.unions>oracle.unions)
    unique_views={id(s['view']):s['view'] for s in plan['witness_sites'].values()}
    view_bytes=sum(a.nbytes for view in unique_views.values() for a in view.values())
    return dict(**round_counts,gpu_installed=1,witness_compiled_view_bytes=view_bytes,witness_site_checks=sum(s['records_per_source']*batch['sources'].shape[1] for s in plan['witness_sites'].values()),witness_argument_checks=sum(s['records_per_source']*batch['sources'].shape[1]*len(s['slots']) for s in plan['witness_sites'].values()),reused_result_slots=sum(int(raw[dst])!=fresh_base+dst for kind,dst,src in plan["operations"] if kind=="fresh"),local_eq_pass=int(local_eq_ok),local_eq_pass_graph_fail=int(local_eq_ok and not passed),missing_union_failures=int('missing_union' in check['errors']),wrong_merge_failures=int('inconsistent_result_class' in check['errors']),constructor_failures=int('unexpected_constructor' in check['errors']),reference_new_constructors=ref.constructions-oracle.constructions,reference_new_unions=ref.unions-oracle.unions,reference_novel_frames=int(novel),prediction_pass_novel_frames=int(passed and novel),prediction_graph_pass=int(passed),cpu_corrected=int(not passed),corrected_graph_pass=int(correction_pass),token_refresh_required=int(refresh),
        downstream_expected=len(expected),downstream_observed=len(observed),downstream_false_positive=len(observed-expected)+unknown,downstream_missed=len(expected-observed),
        downstream_incomplete=int(not bool(downstream['complete'])),cpu_audit_seconds=cpu_seconds,correction_wall_seconds=time.perf_counter()-correction_started,rolled_back=int(bool(verdict['rolled_back'])))
