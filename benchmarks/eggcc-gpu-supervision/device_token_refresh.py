"""Refresh class-balanced floating Cell state from current on-device slots.

This is encoding, not learned inference or a semantic completion certificate.
The output matches the representation used to train the current ridge models.
"""


def encode_batch(roots,sorts,eq_slots,valid,roles,scalar_codes,xp):
    eq_valid=eq_slots & valid
    same=((roots[:,:,None]==roots[:,None,:])&(sorts[:,:,None]==sorts[:,None,:])
          &eq_valid[:,:,None]&eq_valid[:,None,:])
    size=xp.maximum(xp.sum(same.astype(xp.float32),axis=2),1)
    context=(same.astype(xp.float32)@roles)/size[:,:,None]
    message=xp.tanh(roles+xp.where(eq_slots[:,:,None],context,scalar_codes))
    message=xp.where(valid[:,:,None],message,0)
    weight=xp.where(eq_slots,1/size,1)*valid.astype(xp.float32)
    count=xp.maximum(xp.sum(weight,axis=1),1)
    first=xp.sum(message*weight[:,:,None],axis=1)/xp.sqrt(count[:,None])
    second=xp.sum(message*message*weight[:,:,None],axis=1)/count[:,None]
    return xp.tanh(xp.concatenate([first,second],axis=1))


def refresh(state,sorts,eq_slots,required,roles,scalar_codes,scalar_valid,eq_settled,xp):
    dirty=state.get('token_dirty',xp.zeros_like(state['present']))
    wanted=state['present']&state['visible']&dirty
    from device_slot_owners import shape,read,has
    n,width=shape(state);rows=xp.arange(n)[:,None];slots=xp.arange(width)[None,:]
    roots=read(state,'slot_roots' if has(state,'slot_roots') else 'slots',rows,slots,xp)
    available=read(state,'slot_valid',rows,slots,xp)
    missing=xp.any(required & ~available,axis=1)
    bad_scalar=required&~eq_slots&(~scalar_valid|~xp.all(xp.isfinite(scalar_codes),axis=2))
    invalid_eq=required&eq_slots&((roots<0)|(sorts<0))
    valid=available&required
    token=encode_batch(roots,sorts,eq_slots,valid,roles,scalar_codes,xp)
    finite=xp.all(xp.isfinite(token),axis=1)
    ready=(wanted & state['settled'] & eq_settled & ~missing & ~xp.any(bad_scalar|invalid_eq,axis=1) & finite)
    output=dict(state)
    output['tokens']=xp.where(ready[:,None],token,state['tokens'])
    output['token_dirty']=dirty & ~ready
    return output,dict(refreshed=ready,missing_slots=wanted&missing,
        missing_scalar=wanted&xp.any(bad_scalar,axis=1),invalid_eq=wanted&xp.any(invalid_eq,axis=1),
        nonfinite=wanted&~finite,needs_attention=xp.any(wanted&~ready))
