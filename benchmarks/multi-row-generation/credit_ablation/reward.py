"""Detached team rewards for a terminated two-Run trajectory.

Call only after the actor has emitted both stages. Targets use source witness
identities, while the second action indexes an actual generated parent slot.
No model forward, assignment solver, CPU transfer or reference repair occurs
in this function.
"""
import torch


def _stage_counts(bound, semantic, live, required):
    """Masks are [B, emitted_slot, source_obligation], not independent fields."""
    bound_targets = bound.any(1)
    semantic_targets = semantic.any(1)
    active = live.sum(1, dtype=torch.int32)
    legal = bound.any(-1).sum(1, dtype=torch.int32)
    unique = bound_targets.sum(1, dtype=torch.int32)
    correct = semantic_targets.sum(1, dtype=torch.int32)
    obligations = required.sum(1, dtype=torch.int32)
    exact = (correct == obligations) & (active == obligations)
    coverage = correct.float() / obligations.clamp_min(1).float()
    return dict(obligations=obligations, active_outputs=active, valid_unique=unique,
                unique_correct=correct, missing=obligations-unique, semantic_missing=obligations-correct,
                duplicates=legal-unique, illegal=active-legal, waste=active-correct,
                complete=exact, coverage=coverage), semantic_targets


def _actions(stage, target):
    active = stage['active']
    pointers = stage['pointers']
    rows = stage['rows']
    shape = tuple(active.shape)
    if active.ndim != 2 or target.ndim != 3 or target.shape[0] != active.shape[0]:
        raise ValueError('expected batched terminated token sequences and batched source witnesses')
    if tuple(pointers.shape) != (*shape,2) or tuple(rows.shape) != (*shape,target.shape[2]-3):
        raise ValueError('expected discrete two-pointer actions and full projected output rows')
    if active.shape[1] == 0 or target.shape[1] == 0:
        raise ValueError('slot capacities must be positive')
    if pointers.dtype.is_floating_point or active.dtype.is_floating_point:
        raise TypeError('pass categorical sampled actions, not pointer logits or probabilities')
    if any(v.device != target.device for v in (active, pointers, rows)):
        raise ValueError('source targets and actions must be on the same device')
    return active.eq(1), pointers, rows


@torch.no_grad()
def team_reward(first, second, target1, target2):
    """Return a float32 reward vector [B] and per-graph diagnostic components.

    Target format [active,left,right,...payload]. The finish target left index
    names a source make obligation. The actual finish pointer instead names a
    physical emitted make slot; we resolve its *real* provenance before scoring.
    The source sets are assumed to contain each legal witness exactly once.
    For a valid-empty source set coverage is zero and no nonempty bonus applies.
    """
    active1, p1, row1 = _actions(first, target1)
    active2, p2, row2 = _actions(second, target2)
    if target1.shape[0]!=target2.shape[0] or target1.device!=target2.device:
        raise ValueError('both Runs must cover the same batch and device')
    req1, req2 = target1[...,0].eq(1), target2[...,0].eq(1)
    equal_pointers = p1[:,:,None,:].eq(target1[:,None,:,1:3]).all(-1)
    bound1 = (active1[:,:,None] & req1[:,None,:]) & equal_pointers
    right_row1 = row1[:,:,None,:].eq(target1[:,None,:,3:]).all(-1)
    correct1 = bound1 & right_row1
    run1, provided = _stage_counts(bound1, correct1, active1, req1)

    # `argmax` only identifies a source obligation for an already *generated*
    # make pointer pair. Empty matches remain invalid in parent_bound/parent_ok.
    source_of_slot = bound1.to(torch.int32).argmax(-1)
    pi = p2[...,0]
    in_range = pi.ge(0) & pi.lt(p1.shape[1])
    slot = pi.clamp(0,p1.shape[1]-1).long()
    selected_source = source_of_slot.gather(1,slot)
    parent_bound = in_range & bound1.any(-1).gather(1,slot)
    parent_ok = in_range & correct1.any(-1).gather(1,slot)
    finish_sources = target2[...,1]
    requests = target2[...,2]
    bound2 = (active2[:,:,None] & parent_bound[:,:,None] & req2[:,None,:]
              & selected_source[:,:,None].eq(finish_sources[:,None,:])
              & p2[...,1,None].eq(requests[:,None,:]))
    right_row2 = row2[:,:,None,:].eq(target2[:,None,:,3:]).all(-1)
    correct2 = bound2 & parent_ok[:,:,None] & right_row2
    run2, consumed = _stage_counts(bound2, correct2, active2, req2)

    # Count one required/consumed source parent per distinct producer binding.
    # Sharing a parent between different true Requests earns separate finish
    # coverage but cannot multiply the consumed-parent numerator.
    domain = torch.arange(target1.shape[1], device=target1.device)
    requested_parents = finish_sources[:,:,None].eq(domain) & req2[:,:,None]
    required_parent_mask = requested_parents.any(1)
    consumed_parent_mask = (requested_parents & consumed[:,:,None]).any(1)
    required = required_parent_mask.sum(-1,dtype=torch.int32)
    used = consumed_parent_mask.sum(-1,dtype=torch.int32)
    parent_fraction = used.float() / required.clamp_min(1).float()
    ready_slot = provided.gather(1,finish_sources.clamp(0,target1.shape[1]-1).long())
    unavailable = (req2 & ~ready_slot).sum(-1,dtype=torch.int32)
    exact_finish = run2['complete'] & run2['obligations'].gt(0)
    waste1, waste2 = run1['waste'].float()/active1.shape[1], run2['waste'].float()/active2.shape[1]
    reward = (run1['coverage'] + 2*run2['coverage'] + parent_fraction + exact_finish.float()
              - waste1 - waste2 - 1) / 4
    parts = {f'{name}_{key}':value for name,stage in [('run1',run1),('run2',run2)]
             for key,value in stage.items()}
    parts.update(required_parents=required, consumed_parents=used, consumed_parent_fraction=parent_fraction,
                 unavailable_parent_obligations=unavailable,parent_ready=unavailable.eq(0),
                 exact_nonempty_finish=exact_finish, C1=run1['coverage'], C2=run2['coverage'],
                 P=parent_fraction, E2=exact_finish.float(), W1=waste1, W2=waste2)
    return reward, parts
