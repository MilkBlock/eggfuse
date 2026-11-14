"""Covered Run handshake between nested schedule and device Cell execution.

Inputs must already represent the initialized graph with no pending source
operations. Coverage is a caller/compiler proof obligation; existing real
single-source catalogs cannot certify it. No ownership proof is invented here.
"""
from device_slot_owners import ensure_roots
from device_schedule import initial,current,tick
from device_entry_round import run_round
from device_constructor_completion import complete


def run(state,blocks,model,completion,schedule,repeat_slots,query_covered,next_id,limit,quota,external_complete,eq_settled,ticks,xp,eq_context=None,eq_rounds=4,continuation=None,query_kernel=None,takeover_catalog=None,takeover_budget=None,stage_models=None):
    if ticks<1:raise ValueError('positive tick budget required')
    if query_covered.shape[0]<1:raise ValueError('stage coverage array required')
    state=ensure_roots(state,xp)
    if continuation is None:
        machine=initial(schedule,repeat_slots,xp);opened=xp.array(False);changed=xp.array(False);failed=xp.array(False)
    else:
        machine=continuation['control'];opened=continuation['open_run'];changed=continuation['unreported_change'];failed=continuation['failed_run']
    captures=[]
    logs={k:[] for k in ('stage','query_started','query_failed','run_done','run_changed','new_tokens','new_constructors','new_equivalences')}
    if takeover_catalog is not None:
        for key in ('takeover_attempted','takeover_released','takeover_copied_fields','takeover_blocked'):logs[key]=[]
    if stage_models is not None:logs['missing_stage_model']=[]
    for _ in range(ticks):
        stage,_=current(machine,schedule,xp);in_run=stage>=0;begin=in_run&~opened
        # Only the first tick of a Run takes a query snapshot. Waiting ticks
        # finish its effects without rematching against newly produced facts.
        active_model=model;model_ready=xp.array(True)
        if stage_models is not None:
            from device_stage_models import select
            active_model,model_ready=select(stage_models,stage,xp)
        query_stage=xp.where(begin&model_ready,stage,-1)
        key_context=None if eq_context is None else dict(eq_context,types=completion['key_types'],settled=eq_settled)
        if query_kernel is None:
            queried,q=run_round(state,blocks,active_model,query_stage,xp,key_context=key_context)
        else:
            queried,q=query_kernel(state,blocks,active_model,query_stage,xp,external_complete=external_complete,eq_settled=eq_settled,key_context=key_context)
        if 'captures' in q:
            captures.append(tuple(dict(c,recorded=begin&c['enabled'],stage=stage) for c in q['captures']))
        error=~model_ready
        if stage_models is not None:logs['missing_stage_model'].append(begin&~model_ready)
        for key in ('stale_source','nonfinite','unsettled_source','capacity','missing_witness','transfer_blocked'):
            error=error|xp.any(q[key])
        error=error|xp.any(q['invalid_key'])|q['key_context_pending']
        failed=failed|(begin&error)
        candidate,new_id,e=complete(queried,completion,next_id,limit,quota,external_complete,eq_settled,xp,eq_context,eq_rounds)
        # Failed enumeration cannot commit a partial Run's effects or IDs.
        # Admitted instances remain pending evidence for explicit recovery.
        candidate={k:xp.where(~failed,candidate[k],v) for k,v in queried.items()}
        new_id=xp.where(~failed,new_id,next_id)
        for key in ('new_constructors','new_equivalences'):e[key]=xp.where(~failed,e[key],0)
        e['semantic_changed']=~failed&e['semantic_changed']
        if eq_context is not None:
            e['eq_context']={k:xp.where(~failed,e['eq_context'][k],v) for k,v in eq_context.items()}
            e['eq_settled']=xp.where(~failed,e['eq_settled'],eq_settled)
        changed=changed|(in_run&e['semantic_changed'])
        after_eq=e.get('eq_settled',eq_settled)
        safe=xp.clip(stage,0,query_covered.shape[0]-1)
        covered=(stage<query_covered.shape[0])&query_covered[safe]
        done=in_run&(opened|begin)&covered&external_complete&after_eq&~e['needs_attention']&~failed
        if takeover_catalog is not None:
            from device_matched_takeover import finish
            candidate,tm=finish(candidate,takeover_catalog,done,xp,budget=takeover_budget)
            for key,value in tm.items():logs['takeover_'+key].append(value)
        machine,control=tick(machine,schedule,done,changed,xp)
        for key,value in dict(stage=stage,query_started=begin,query_failed=begin&error,run_done=done,run_changed=done&changed,
                              new_tokens=xp.where(begin,q['new_tokens'],0),new_constructors=xp.where(in_run,e['new_constructors'],0),
                              new_equivalences=xp.where(in_run,e['new_equivalences'],0)).items():logs[key].append(value)
        state={k:xp.where(in_run,candidate[k],v) for k,v in state.items()}
        next_id=xp.where(in_run,new_id,next_id)
        if eq_context is not None:eq_context={k:xp.where(in_run,e['eq_context'][k],v) for k,v in eq_context.items()}
        eq_settled=xp.where(in_run,after_eq,eq_settled)
        opened=(opened|begin)&~done;changed=changed&~done;failed=failed&~done
    _,finished=current(machine,schedule,xp)
    result={k:xp.stack(v) for k,v in logs.items()}
    result.update(finished=finished,open_run=opened,failed_run=failed,unreported_change=changed,control=machine,eq_settled=eq_settled)
    if captures:result['query_captures']=tuple(captures)
    if eq_context is not None:result['eq_context']=eq_context
    return state,next_id,result
