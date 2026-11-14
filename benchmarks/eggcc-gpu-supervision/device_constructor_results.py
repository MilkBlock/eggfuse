"""Batched constructor identities for Cell-owned result slots.

Keys/witnesses are ephemeral views of template fields, not a new persistent fact
store. Inputs must be exact current typed keys at one frozen completion boundary.
This bounded pairwise implementation is a correctness prototype, not a fast
large-graph index or a replacement for floating Cell-state inference.
"""


def resolve(keys,active,witness_keys,witness_ids,witness_roots,witness_live,
            next_id,limit,quota,xp):
    """Return actual existing or newly allocated identities, entirely on device.

    Allocation namespace [next_id, limit) must have been reserved above every
    pre-existing identity, including external inputs not in witness_keys.
    A repeated key with unequal current result roots is pending congruence, not
    permission to select one arbitrarily. Such groups receive no result.
    """
    n=keys.shape[0];w=witness_keys.shape[0]
    if n<1 or w<1:raise ValueError('use at least one masked candidate and witness lane')
    if keys.shape[1]!=witness_keys.shape[1]:raise ValueError('constructor key width mismatch')
    for value in (keys,witness_keys,witness_ids,witness_roots):
        if value.dtype not in (xp.int32,xp.int64):raise ValueError('exact signed integer keys and identities required')
    matches=xp.all(keys[:,None,:]==witness_keys[None,:,:],axis=2)&witness_live[None,:]
    found=xp.any(matches,axis=1);choice=xp.argmax(matches.astype(xp.int32),axis=1)
    chosen_roots=witness_roots[choice]
    conflict=xp.any(matches & (witness_roots[None,:]!=chosen_roots[:,None]),axis=1)
    valid_witness=xp.all(~witness_live | ((witness_ids>=0)&(witness_roots>=0)))
    # This detects overlapping visible IDs; the full namespace reservation
    # remains an explicit caller obligation, not inferred from a partial view.
    namespace=(next_id>=0)&(next_id<=limit)&(quota>=0)&valid_witness&xp.all(~witness_live | (witness_ids<next_id))
    eligible=active & ~conflict & namespace
    equal=xp.all(keys[:,None,:]==keys[None,:,:],axis=2)
    earlier=xp.arange(n)[None,:]<xp.arange(n)[:,None]
    fresh=eligible & ~found
    first=fresh & ~xp.any(equal & earlier & fresh[None,:],axis=1)
    rank=xp.cumsum(first.astype(xp.int32))-1
    available=xp.minimum(xp.maximum(limit-next_id,0),xp.maximum(quota,0))
    allocate=first & (rank<available)
    # Avoid overflowing even the unselected branch of a tensor where.
    allocated_ids=next_id+xp.where(allocate,rank,0)
    group=equal & first[None,:]
    leader=xp.argmax(group.astype(xp.int32),axis=1)
    group_accepted=xp.any(group & allocate[None,:],axis=1)
    ready=eligible & (found | group_accepted)
    result=xp.where(found,witness_ids[choice],allocated_ids[leader])
    result=xp.where(ready,result,-1)
    count=xp.sum(allocate.astype(xp.int32))
    result_root=xp.where(ready,xp.where(found,chosen_roots,allocated_ids[leader]),-1)
    return dict(result=result,result_root=result_root,ready=ready,new_owner=allocate,
        reused=eligible&found,shared_new=ready&~found&~allocate,
        conflict=active&conflict,capacity=fresh&~group_accepted,
        invalid_namespace=xp.any(active)&~namespace,next_id=next_id+count,
        needs_attention=xp.any(active&~ready))


def execute_site(state,site,witness,next_id,limit,quota,xp):
    """One compiled constructor site across Cell instances, no node allocation.

    effect_pc is source effect order, not a new rule scheduler. All supplied
    witnesses and argument identities must share the same settled Eq snapshot.
    This executes a constructor, not surrounding union/mutable/scalar operations.
    """
    from device_slot_owners import shape,read,has,dtype,prepare_write,write_slot
    rows,width=shape(state);row=xp.arange(rows)
    if not 0<=site['dst']<width or any(not 0<=a<width for a in site['args']):
        raise ValueError('compiled constructor slot out of bounds')
    selected=(state['present'] & state['active'] & state['visible'] & ~state['settled']
              & (state['keys'][:,0]==site['rule']) & (state['effect_pc']==site['operation']))
    args=read(state,'slot_roots' if has(state,'slot_roots') else 'slots',row[:,None],xp.array(site['args'],dtype=xp.int32)[None,:],xp)
    available=xp.all(read(state,'slot_valid',row[:,None],xp.array(site['args'],dtype=xp.int32)[None,:],xp),axis=1)
    if 'literal_ids' in site:
        literals=xp.array(site['literal_ids'],dtype=xp.int32);constant=literals>=0
        args=xp.where(constant[None,:],literals[None,:],args)
        slot_live=read(state,'slot_valid',row[:,None],xp.array(site['args'],dtype=xp.int32)[None,:],xp)
        available=xp.all(slot_live|constant[None,:],axis=1)&xp.all(~constant|(literals<next_id))
    keys=xp.concatenate([xp.full((rows,1),site['table'],dtype=dtype(state)),args],axis=1)
    view_complete=xp.array(witness.get('complete',True),dtype=xp.bool_)
    storage=prepare_write(state,selected&available&view_complete,xp)
    outcome=resolve(keys,storage['ready'],witness['keys'],witness['ids'],witness['roots'],witness['live'],next_id,limit,quota,xp)
    values=dict(slots=outcome['result'],slot_roots=outcome['result_root'],slot_valid=xp.ones(rows,xp.bool_))
    for column in ('scalar_numbers','scalar_numeric','scalar_valid','scalar_codes'):
        if has(state,column):values[column]=xp.zeros_like(read(state,column,row,xp.full(rows,site['dst'],xp.int32),xp))
    output=write_slot(state,site['dst'],values,outcome['ready'],xp,storage)
    if 'tokens' in state or 'token_dirty' in state:
        output['token_dirty']=state.get('token_dirty',xp.zeros_like(state['present'])) | outcome['ready']
    outcome['storage_blocked']=storage['blocked']
    output['effect_pc']=state['effect_pc']+outcome['ready'].astype(xp.int32)
    output['settled']=state['settled'] | (outcome['ready'] & site['last_effect'])
    outcome['incomplete_witness_view']=selected&~view_complete
    outcome['missing_argument']=selected&~available
    outcome['needs_attention']=outcome['needs_attention'] | xp.any(outcome['missing_argument'] | outcome['incomplete_witness_view'] | outcome['storage_blocked'])
    return output,outcome
