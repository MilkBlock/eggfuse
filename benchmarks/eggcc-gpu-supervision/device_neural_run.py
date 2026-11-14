"""Device admissions against one sealed source-Run query snapshot.

Exhausting snapshot candidates is not a semantic saturation certificate. The
caller still owes completion, boundary audit and original schedule handling.
"""
from device_neural_step import advance


def execute(state,roots,next_id,frames,plans,model,head,attempts,xp,enabled=True,capture=False):
    if type(attempts)is not int or attempts<1:raise ValueError('positive static attempt budget required')
    snapshot=state;attention=xp.array(False);exhausted=xp.array(True);admitted=xp.array(0,xp.int32);trace=[]
    allowed=xp.array(enabled,dtype=xp.bool_)
    for rule_id,query,frame in plans:
        done=xp.array(False)
        for _ in range(attempts):
            state,roots,next_id,event=advance(state,roots,next_id,frames,query,frame,rule_id,model,head,
                allowed&~attention&~done,xp,query_state=snapshot,capture=capture)
            done=done|event['no_novel_proposal'];attention=attention|event['needs_attention']
            admitted=admitted+event['admitted'].astype(xp.int32);trace.append((rule_id,event))
            xp.eval(state,roots,next_id,event,done,attention,admitted)
        exhausted=exhausted&done
        # Do not reorder a later rule ahead of an unfinished earlier rule.
        allowed=allowed&done
    return state,roots,next_id,dict(query_exhausted=xp.array(enabled)&exhausted&~attention,
        needs_attention=attention,attempt_budget_exhausted=xp.array(enabled)&~exhausted&~attention,
        admitted=admitted,trace=trace)
