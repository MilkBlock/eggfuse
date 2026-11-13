"""Covered Run handshake between nested schedule and device Cell execution.

Inputs must already represent the initialized graph with no pending source
operations. Coverage is a caller/compiler proof obligation; existing real
single-source catalogs cannot certify it. No ownership proof is invented here.
"""
from device_schedule import initial,current,tick
from device_entry_round import run_round
from device_constructor_completion import complete


def run(state,blocks,model,completion,schedule,repeat_slots,query_covered,next_id,limit,quota,external_complete,eq_settled,ticks,xp,eq_context=None,eq_rounds=4,continuation=None,query_kernel=None):
    if ticks<1:raise ValueError('positive tick budget required')
    if query_covered.shape[0]<1:raise ValueError('stage coverage array required')
    state=dict(state,slot_roots=state.get('slot_roots',state['slots']),token_dirty=state.get('token_dirty',xp.zeros_like(state['present'])))
    if continuation is None:
        machine=initial(schedule,repeat_slots,xp);opened=xp.array(False);changed=xp.array(False);failed=xp.array(False)
    else:
        machine=continuation['control'];opened=continuation['open_run'];changed=continuation['unreported_change'];failed=continuation['failed_run']
    logs={k:[] for k in ('stage','query_started','run_done','run_changed','new_tokens','new_constructors','new_equivalences')}
    for _ in range(ticks):
        stage,_=current(machine,schedule,xp);in_run=stage>=0;begin=in_run&~opened
        # Only the first tick of a Run takes a query snapshot. Waiting ticks
        # finish its effects without rematching against newly produced facts.
        if query_kernel is None:
            queried,q=run_round(state,blocks,model,xp.where(begin,stage,-1),xp)
        else:
            queried,q=query_kernel(state,blocks,model,xp.where(begin,stage,-1),xp,external_complete=external_complete,eq_settled=eq_settled)
        candidate,new_id,e=complete(queried,completion,next_id,limit,quota,external_complete,eq_settled,xp,eq_context,eq_rounds)
        error=xp.array(False)
        for key in ('stale_source','nonfinite','unsettled_source','capacity','missing_witness','transfer_blocked'):
            error=error|xp.any(q[key])
        failed=failed|(begin&error)
        changed=changed|(in_run&e['semantic_changed'])
        after_eq=e.get('eq_settled',eq_settled)
        safe=xp.clip(stage,0,query_covered.shape[0]-1)
        covered=(stage<query_covered.shape[0])&query_covered[safe]
        done=in_run&(opened|begin)&covered&external_complete&after_eq&~e['needs_attention']&~failed
        machine,control=tick(machine,schedule,done,changed,xp)
        for key,value in dict(stage=stage,query_started=begin,run_done=done,run_changed=done&changed,
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
    if eq_context is not None:result['eq_context']=eq_context
    return state,next_id,result
