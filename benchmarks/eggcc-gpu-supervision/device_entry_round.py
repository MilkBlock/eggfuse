"""Snapshot rounds over static Entry blocks, with one joint admission.

The Python block loop unrolls compiled GPU dataflow. It does not inspect device
values or provide successful matches. This is not a full source Run controller:
ordered RHS effects, repair and cross-Run visibility remain external obligations.
"""
from device_entry_transition import propose
from device_token_commit import commit


def run_round(state,blocks,model,stage,xp):
    if not blocks:raise ValueError('empty catalog is not proof of closure')
    candidates=[]
    for plan,inputs,coefficients in blocks:
        p,_=propose(state,plan,inputs,coefficients,model,stage,xp)
        candidates.append(p)
    fields=candidates[0].keys()
    if any(p.keys()!=fields for p in candidates):raise ValueError('inconsistent candidate payload layouts')
    combined={key:xp.concatenate([p[key] for p in candidates],axis=0) for key in fields}
    # All sources belong to the original snapshot. Competition and duplicate
    # selection span every Entry, not just one local proposal block.
    out,marks=commit(state,combined,xp)
    marks['proposed_matches']=xp.sum(combined['matched'].astype(xp.int32))
    marks['new_tokens']=xp.sum(marks['accepted'].astype(xp.int32))
    return out,marks


def run_rounds(state,blocks,model,stage,rounds,xp):
    if rounds<1:raise ValueError('positive static round budget required')
    counts=[];attention=[]
    for _ in range(rounds):
        state,marks=run_round(state,blocks,model,stage,xp)
        counts.append(marks['new_tokens']);attention.append(marks['needs_attention'])
    return state,dict(new_tokens=xp.stack(counts),needs_attention=xp.stack(attention),
                      last_round_admitted=counts[-1]>0)
