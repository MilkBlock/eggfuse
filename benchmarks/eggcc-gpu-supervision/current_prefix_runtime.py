"""Current-state learned prefix routing into the existing Cell effect engine.

Model choices are audited proposals. Exact lifetime/Entry checks stay active.
"""
from device_prefix_match import expand
from device_slot_owners import read,shape
from device_current_cell_inputs import current_inputs
from neural_device_candidates import candidates


class PrefixRuntime:
    template_only=True

    def __init__(self,network,capacity=32):
        self.network=network;self.capacity=capacity

    def select(self,state,frames,plan,views,xp):
        info=current_inputs(state,frames,xp)
        n,w=shape(state);rows=xp.arange(n)[:,None];slots=xp.arange(w)[None,:]
        rid=xp.clip(state['keys'][:,0],0,len(frames['roles'])-1)
        bank=dict(roots=read(state,'slot_roots',rows,slots,xp),roles=frames['roles'][rid],
                  mask=info['mask'],slot_valid=read(state,'slot_valid',rows,slots,xp))
        pools=[]
        for view in views:
            roots=view['value_roots'][view['pick']]
            padding=plan['fields']-roots.shape[1]
            roots=xp.concatenate([roots,xp.full((len(roots),padding),-1,xp.int32)],axis=1)
            indices=xp.arange(len(roots))
            pools.append(dict(roots=roots,entries=xp.stack([indices,indices],axis=1),live=view['selected']))
        result=expand(bank,pools,xp.array(plan['request']),self.network,plan['atoms'],plan['fields'],self.capacity,xp)
        return dict(indices=result['entries'][:,:len(views),0],live=result['live'],
                    complete=result['complete']&info['complete'],overflow=result['overflow'])

    def current_candidate_batch(self,state,frames,plan,xp):
        if 'owner_token_blocks' in state:raise ValueError('prefix runtime requires ordinary Cell projection')
        temporary=dict(state,tokens=xp.zeros((len(state['present']),128),xp.float32),
                       token_dirty=xp.zeros_like(state['present']))
        return candidates(temporary,frames,plan,xp.array(True),xp.array(True),xp,select_entries=self.select)

    def transition(self,tokens,edges,mask,request,relations):
        # The network has already chosen Entry tuples; no second classifier.
        import mlx.core as mx
        return mx.ones(len(tokens)),mx.zeros((len(tokens),128))
