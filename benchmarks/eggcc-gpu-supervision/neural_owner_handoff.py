"""Adopt a generated token together with a proven sealed-payload takeover.

The target's effects and exact interface must already be completed/certified.
This is not neural authorization of RHS execution or logical fact retirement.
A rejected/stale proposal changes neither the token nor ownership metadata.
"""
from device_slot_owners import transfer


def handoff(state,plan,source,target,source_generation,target_generation,
            logit,token,certified,quiescent,xp):
    finite=xp.all(xp.isfinite(token))&xp.isfinite(logit)
    enabled=certified&finite&(logit>=0)&quiescent
    out,marks=transfer(state,plan,source,target,source_generation,target_generation,enabled,xp)
    n=len(state['tokens']);t=xp.clip(target,0,n-1)
    write=(xp.arange(n)==t)&marks['transferred']
    out['tokens']=xp.where(write[:,None],token[None,:],state['tokens'])
    return out,dict(marks,token_adopted=marks['transferred'],uncertified=~certified,
                    invalid_prediction=~finite,model_rejected=logit<0)
