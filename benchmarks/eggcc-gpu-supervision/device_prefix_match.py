"""Bounded GPU prefix expansion over current Cell Entry pools.

Fixed template depth; learned choices remain proposals. Overflow and nonfinite
scores block completeness. Exact whole-match acceptance is audited separately.
"""
from cell_context_features import port_context


def expand(bank,pools,request,model,atoms,ports,capacity,xp):
    if capacity<1 or not 0<len(pools)<=atoms:raise ValueError('invalid prefix capacity/depth')
    previous=xp.full((capacity,atoms,ports),-1,xp.int32)
    messages=xp.zeros((capacity,atoms,ports,64),xp.float32)
    entries=xp.full((capacity,atoms,2),-1,xp.int32)
    live=xp.arange(capacity)==0
    overflow=xp.array(False);nonfinite=xp.array(False);evaluated=xp.array(0,xp.int32);scheduled=0;rejected=xp.array(False)
    for depth,pool in enumerate(pools):
        roots=pool['roots'];n=len(roots)
        if n<1:raise ValueError('pools require at least one masked padding row')
        context=port_context(bank,roots,xp)
        links=(roots[None,:,None,:,None]==previous[:,None,:,None,:])&(
            roots[None,:,None,:,None]>=0)&(previous[:,None,:,None,:]>=0)
        shape=(capacity,n)
        x=xp.concatenate([
            xp.broadcast_to(request,shape+(64,)),
            xp.broadcast_to((xp.arange(atoms)==depth).astype(xp.float32),shape+(atoms,)),
            xp.broadcast_to(context[None,:,:,:],shape+(ports,64)).reshape(*shape,-1),
            xp.broadcast_to(messages[:,None,:,:,:],shape+(atoms,ports,64)).reshape(*shape,-1),
            links.astype(xp.float32).reshape(*shape,-1)],axis=-1)
        scheduled+=capacity*n
        scores=model(x.reshape(capacity*n,-1))[:,0].reshape(shape)
        eligible=live[:,None]&pool['live'][None,:]
        nonfinite=nonfinite|xp.any(eligible&~xp.isfinite(scores))
        chosen=eligible&xp.isfinite(scores)&(scores>=0)
        rejected=rejected|xp.any(eligible&~chosen)
        count=xp.sum(chosen.astype(xp.int32));overflow=overflow|(count>capacity)
        evaluated=evaluated+xp.sum(eligible.astype(xp.int32))
        order=xp.sort(xp.where(chosen.reshape(-1),xp.arange(capacity*n),capacity*n))[:capacity]
        next_live=order<capacity*n;safe=xp.clip(order,0,capacity*n-1)
        parent=safe//n;child=safe%n;slot=xp.arange(atoms)==depth
        previous=xp.where(slot[None,:,None],roots[child,None,:],previous[parent])
        messages=xp.where(slot[None,:,None,None],context[child,None,:,:],messages[parent])
        entries=xp.where(slot[None,:,None],pool['entries'][child,None,:],entries[parent])
        live=next_live
    return dict(entries=entries,live=live,overflow=overflow,nonfinite=nonfinite,
                complete=~overflow&~nonfinite&~rejected,proposal_complete=~overflow&~nonfinite,active_choices=evaluated,scheduled_choices=xp.array(scheduled,xp.int32))
