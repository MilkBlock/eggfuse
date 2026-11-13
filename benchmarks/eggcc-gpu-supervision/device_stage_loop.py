"""Bounded device stage loop with explicit coverage gates.

This consumes an already lowered stage schedule. It does not translate egglog's
nested schedules or manufacture query-coverage proofs. Existing single-source
catalogs remain uncertified, so their default controls cannot advance a stage.
"""
import numpy as np
from device_entry_round import run_round
from device_constructor_completion import complete


def compile_controls(lowered,stage_schedule):
    if not stage_schedule:raise ValueError('nonempty stage schedule required')
    if any(not 0<=s<len(lowered['stages']) for s in stage_schedule):raise ValueError('unknown stage')
    return dict(schedule=np.array(stage_schedule,np.int32),
                query_covered=np.full(len(stage_schedule),bool(lowered['closure_authorized']),bool))


def run(state,blocks,model,completion,controls,next_id,limit,quota,external_complete,eq_settled,rounds,xp,eq_context=None,eq_rounds=4):
    if rounds<1:raise ValueError('positive static round budget required')
    count=controls['schedule'].shape[0]
    if count<1 or controls['query_covered'].shape!=(count,):raise ValueError('stage coverage layout mismatch')
    # Bootstrap obligations must be completed before a first query snapshot.
    state,next_id,initial=complete(state,completion,next_id,limit,quota,external_complete,eq_settled,xp,eq_context,eq_rounds)
    if eq_context is not None:eq_context=initial['eq_context'];eq_settled=initial['eq_settled']
    cursor=xp.array(0,dtype=xp.int32);history=[];created=[];advanced=[];blocked=[]
    for _ in range(rounds):
        running=cursor<count;safe=xp.minimum(cursor,count-1)
        stage=xp.where(running,controls['schedule'][safe],-1)
        key_context=None if eq_context is None else dict(eq_context,types=completion['key_types'],settled=eq_settled)
        queried,query=run_round(state,blocks,model,stage,xp,key_context=key_context)
        candidate,new_id,effects=complete(queried,completion,next_id,limit,quota,external_complete,eq_settled,xp,eq_context,eq_rounds)
        after_eq=effects.get('eq_settled',eq_settled)
        failed=xp.array(False)
        for key in ('stale_source','nonfinite','unsettled_source','capacity','missing_witness','transfer_blocked'):
            failed=failed|xp.any(query[key])
        failed=failed|xp.any(query['invalid_key'])|query['key_context_pending']
        quiet=(query['new_tokens']==0)&(effects['executed']==0)&(effects['refreshed']==0)
        covered=controls['query_covered'][safe]&external_complete
        advance=running&quiet&covered&after_eq&~effects['needs_attention']&~failed
        history.append(stage);created.append(xp.where(running,query['new_tokens'],0));advanced.append(advance)
        blocked.append(running&(~covered|~after_eq|effects['needs_attention']|failed))
        state={k:xp.where(running,candidate[k],v) for k,v in state.items()}
        next_id=xp.where(running,new_id,next_id)
        if eq_context is not None:
            eq_context={k:xp.where(running,effects['eq_context'][k],v) for k,v in eq_context.items()}
        eq_settled=xp.where(running,after_eq,eq_settled)
        cursor=cursor+advance.astype(xp.int32)
    marks=dict(stage_cursor=cursor,finished=cursor==count,round_budget_consumed=cursor<count,
               stage_history=xp.stack(history),new_tokens=xp.stack(created),advanced=xp.stack(advanced),
               needs_attention=xp.stack(blocked),bootstrap_attention=initial['needs_attention'])
    if eq_context is not None:marks['eq_context']=eq_context
    marks['eq_settled']=eq_settled
    return state,next_id,marks
