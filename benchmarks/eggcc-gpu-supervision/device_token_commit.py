"""Bounded device token admission and activation-owner transfer.

Exact keys are compiler/runtime interface identities, never rounded float tokens.
This kernel consumes device-produced proposals; it does not itself match queries
or prove the supplied transfer coverage. Pairwise dedup is a bounded prototype.
"""


def commit(state, proposals, xp, key_context=None):
    """One snapshot-in/snapshot-out tensor operation, no host value reads.

    present rows retain semantic keys; active rows own continuation work.
    Retired payload is kept for readers. No physical reclamation is claimed.
    A proposal can transfer activation only from a settled, reader-free owner,
    with one admitted successor and an explicit compiled-coverage bit.
    """
    from device_slot_owners import live as owner_live,free_rows,allocate
    capacity = state['keys'].shape[0]; count = proposals['keys'].shape[0]
    if capacity < 1 or count < 1:
        raise ValueError('positive static capacity and proposal count required')
    integer_types=(xp.int32,xp.int64,xp.uint32,xp.uint64)
    if state['keys'].dtype not in integer_types or proposals['keys'].dtype not in integer_types:
        raise ValueError('semantic keys must be exact integers')
    if state['keys'].shape[1] != proposals['keys'].shape[1]:
        raise ValueError('semantic key layout mismatch')
    source = proposals['source']
    in_range = (source >= 0) & (source < capacity)
    safe_source = xp.clip(source, 0, capacity-1)
    stale_token=state.get('token_dirty',xp.zeros_like(state['active']))[safe_source]
    valid_source = (in_range & ~stale_token & state['present'][safe_source] & state['active'][safe_source]
                    & state['visible'][safe_source]
                    & (state['generation'][safe_source] == proposals['generation']))
    valid_source=valid_source&owner_live(state,safe_source,xp)
    finite = xp.all(xp.isfinite(proposals['tokens']), axis=1)
    settled = state['settled'][safe_source]
    multi_source='witness_sources' in proposals
    if multi_source:
        witnesses=proposals['witness_sources'];mask=proposals['witness_valid']
        if witnesses.ndim!=2 or witnesses.shape[0]!=count or witnesses.shape!=mask.shape or witnesses.shape!=proposals['witness_generations'].shape:
            raise ValueError('witness layout mismatch')
        safe=xp.clip(witnesses,0,capacity-1)
        dirty=state.get('token_dirty',xp.zeros_like(state['active']))[safe]
        valid=((witnesses>=0)&(witnesses<capacity)&state['present'][safe]&state['visible'][safe]
               &(state['generation'][safe]==proposals['witness_generations'])&~dirty)
        valid=valid&owner_live(state,safe,xp)
        valid_source=xp.any(mask,axis=1)&xp.all(~mask|valid,axis=1)
        stale_token=xp.any(mask&dirty,axis=1)
        settled=xp.all(~mask|state['settled'][safe],axis=1)
    eligible = proposals['matched'] & valid_source & settled & finite
    # Completed/retired logical keys remain known: repeated derivations are not
    # new facts and may not reactivate work merely by producing another vector.
    candidate_keys=proposals['keys'];resident_keys=state['keys']
    invalid_key=xp.zeros(count,xp.bool_);key_context_pending=xp.array(False)
    if key_context is not None:
        from device_semantic_keys import comparison_view
        candidate_keys,valid_keys=comparison_view(candidate_keys,key_context,xp)
        resident_keys,valid_resident=comparison_view(resident_keys,key_context,xp)
        key_context_pending=~xp.array(key_context['settled'],dtype=xp.bool_)|xp.any(state['present']&~valid_resident)
        invalid_key=proposals['matched']&~valid_keys
        eligible=eligible&valid_keys&~key_context_pending
    existing = xp.all(candidate_keys[:,None,:] == resident_keys[None,:,:], axis=2)
    known = xp.any(existing & state['present'][None,:], axis=1)
    equal = xp.all(candidate_keys[:,None,:] == candidate_keys[None,:,:], axis=2)
    earlier = xp.arange(count)[None,:] < xp.arange(count)[:,None]
    prior = xp.any(equal & earlier & eligible[None,:], axis=1)
    novel = eligible & ~known & ~prior
    rank = xp.cumsum(novel.astype(xp.int32))-1
    free = ~state['present']; free_rank = xp.cumsum(free.astype(xp.int32))-1
    free_count = xp.sum(free.astype(xp.int32))
    owner_capacity=xp.array(count) if 'slot_owner' not in state else xp.sum(free_rows(state,xp).astype(xp.int32))
    accepted = novel & (rank < free_count) & (rank < owner_capacity)
    write = accepted[:,None] & free[None,:] & (rank[:,None] == free_rank[None,:])
    written = xp.any(write, axis=0)
    # At most one admitted proposal per destination. Indices select exact
    # integer keys; token payload transfer remains floating dense arithmetic.
    pick = xp.argmax(write.astype(xp.int32), axis=0)
    # A source with competing matched successors retains its activation owner,
    # even if one candidate is duplicate or over capacity in this round.
    if multi_source:
        transferable=xp.zeros_like(accepted) # No inferred unique owner or primary-owner competition scan.
    else:
        same_source = source[:,None] == source[None,:]
        competitors = xp.sum((same_source & eligible[None,:]).astype(xp.int32), axis=1)
        transferable = (accepted & proposals['transfer_covered'] & (competitors == 1)
                        & state['settled'][safe_source] & ~state['readers'][safe_source])
    retired = xp.any(transferable[:,None] & (source[:,None] == xp.arange(capacity)[None,:]), axis=0)
    output = dict(state)
    output['keys'] = xp.where(written[:,None], proposals['keys'][pick], state['keys'])
    output['tokens'] = xp.where(written[:,None], proposals['tokens'][pick], state['tokens'])
    if 'slot_owner' in state:
        owned=allocate(state,proposals,accepted,rank,written,pick,xp)
        for key in owned:
            if key.startswith('owner_') or key=='slot_owner':output[key]=owned[key]
    else:
        if 'slots' in proposals:
            output['slots']=xp.where(written[:,None],proposals['slots'][pick],state['slots'])
            output['slot_valid']=xp.where(written[:,None],proposals['slot_valid'][pick],state['slot_valid'])
        for column in ('scalar_numbers','scalar_numeric','scalar_codes','scalar_valid'):
            if column in state:
                if column not in proposals:raise ValueError('proposal lost scalar slot columns')
                mask=written[:,None,None] if state[column].ndim==3 else written[:,None]
                output[column]=xp.where(mask,proposals[column][pick],state[column])
        if 'slot_roots' in state:
            if 'slot_roots' not in proposals:raise ValueError('proposal lost authoritative root slots')
            output['slot_roots']=xp.where(written[:,None],proposals['slot_roots'][pick],state['slot_roots'])
    if 'effect_pc' in state:output['effect_pc']=xp.where(written,0,state['effect_pc'])
    if 'token_dirty' in state:output['token_dirty']=xp.where(written,False,state['token_dirty'])
    output['present'] = state['present'] | written
    output['active'] = (state['active'] & ~retired) | written
    output['visible'] = state['visible'] | written
    # New token completion is separate from query matching. No inherited
    # settlement or generation is guessed from the source float payload.
    output['settled'] = xp.where(written, proposals['completed'][pick], state['settled'])
    output['readers'] = xp.where(written, False, state['readers'])
    output['generation'] = xp.where(written, state['generation']+1, state['generation'])
    marks = dict(accepted=accepted, transferred=transferable,invalid_key=invalid_key,key_context_pending=key_context_pending,
        stale_source=proposals['matched'] & ~valid_source,
        stale_token=proposals['matched'] & stale_token,
        nonfinite=proposals['matched'] & ~finite,
        unsettled_source=proposals['matched'] & valid_source & ~settled,
        capacity=novel & ~accepted,owner_capacity=novel&(rank>=owner_capacity),
        transfer_blocked=accepted & proposals['transfer_covered'] & ~transferable,
        duplicate=eligible & (known | prior))
    # Closure also requires caller-supplied query/effect coverage. This is only
    # "no new admission", never a complete egraph saturation certificate.
    marks['missing_witness']=proposals.get('missing_witness',xp.zeros_like(accepted))
    marks['no_new_admission'] = ~xp.any(accepted)
    marks['needs_attention'] = key_context_pending | xp.any(invalid_key) | xp.any(marks['stale_source'] | marks['nonfinite'] | marks['unsettled_source'] | marks['capacity'] | marks['missing_witness']) | xp.any(output['present'] & output['active'] & (~output['settled'] | output.get('token_dirty',xp.zeros_like(output['active']))))
    return output, marks


def closed_entry_proposals(state, plan, stage, xp, token_values=None):
    """Generate all source-slot x compiled-entry candidates on device.

    plan is a dense lowering for input-only projections. Compiler coverage of
    the full query is required; unknown result/literal routes stay outside this
    lowering. completed means the consumer has no outstanding effects, never a
    prediction of settlement. weights/bias are frozen float transition maps.
    """
    from device_slot_owners import read as read_slot,has as has_slot
    capacity = state['keys'].shape[0]; entries = plan['producer'].shape[0]
    # Candidate shape is fixed; success is computed from live token metadata.
    matched = (state['present'][:,None] & state['active'][:,None]
               & (state['keys'][:,0,None] == plan['producer'][None,:])
               & (stage == plan['stage'][None,:])
               & plan['query_covered'][None,:])
    projection = plan['projection']
    use_slots='destination_projection' in plan
    rows=xp.arange(capacity)[:,None,None]
    payload_keys = read_slot(state,'slots',rows,projection[None,:,:],xp) if use_slots else state['keys'][:,projection]
    missing=xp.zeros_like(matched)
    if use_slots:
        ready=xp.all(read_slot(state,'slot_valid',rows,projection[None,:,:],xp) | ~plan['projection_valid'][None,:,:],axis=2)
        missing=matched & ~ready
        matched=matched & ready
    if 'completion_projection' in plan:
        completion_ready=xp.all(read_slot(state,'slot_valid',rows,plan['completion_projection'][None,:,:],xp) | ~plan['completion_valid'][None,:,:],axis=2)
        missing=missing | (matched & ~completion_ready)
        matched=matched & completion_ready
    if 'projection_valid' in plan:  # Static layout option, not a device predicate.
        payload_keys=xp.where(plan['projection_valid'][None,:,:],payload_keys,-1)
    target = xp.broadcast_to(plan['consumer'][None,:,None],(capacity,entries,1))
    keys = xp.concatenate([target,payload_keys],axis=2)
    if token_values is None:
        values = xp.tanh(xp.matmul(state['tokens'][:,None,None,:],plan['weights'][None,:,:,:]).squeeze(axis=2)+plan['bias'][None,:,:])
    else:
        if token_values.shape != (capacity*entries,state['tokens'].shape[1]):
            raise ValueError('ridge candidate layout mismatch')
        values=token_values
    proposals=dict(keys=keys.reshape(capacity*entries,-1),tokens=values.reshape(capacity*entries,-1),
        source=xp.broadcast_to(xp.arange(capacity)[:,None],(capacity,entries)).reshape(-1),
        generation=xp.broadcast_to(state['generation'][:,None],(capacity,entries)).reshape(-1),
        matched=matched.reshape(-1),
        transfer_covered=xp.broadcast_to(plan['transfer_covered'][None,:],(capacity,entries)).reshape(-1),
        completed=xp.broadcast_to(plan['completed'][None,:],(capacity,entries)).reshape(-1))

    proposals['missing_witness']=missing.reshape(-1)
    if use_slots:
        indices=xp.broadcast_to(plan['destination_projection'][None,:,:],(capacity,entries,plan['destination_projection'].shape[1]))
        values=xp.take_along_axis(payload_keys,indices,axis=2)
        valid=xp.broadcast_to(plan['destination_valid'][None,:,:],values.shape)
        if 'completion_projection' in plan:
            cv=plan['completion_valid'][None,:,:]
            values=xp.where(cv,read_slot(state,'slots',rows,plan['completion_projection'][None,:,:],xp),values)
            valid=valid | cv
        proposals['slots']=xp.where(valid,values,-1).reshape(capacity*entries,-1)
        proposals['slot_valid']=valid.reshape(capacity*entries,-1)
        if has_slot(state,'slot_roots'):
            root_inputs=read_slot(state,'slot_roots',rows,projection[None,:,:],xp)
            root_values=xp.take_along_axis(root_inputs,indices,axis=2)
            if 'completion_projection' in plan:
                root_values=xp.where(plan['completion_valid'][None,:,:],read_slot(state,'slot_roots',rows,plan['completion_projection'][None,:,:],xp),root_values)
            proposals['slot_roots']=xp.where(valid,root_values,-1).reshape(capacity*entries,-1)
    return proposals
