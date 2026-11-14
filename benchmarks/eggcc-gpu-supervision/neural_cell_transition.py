"""Learned Cell encoder and relation-conditioned transition on MLX GPU.

All loops are fixed architecture depth. Exact identities only define input
connectivity; no IDs are embedded or predicted as floats. This module proposes
candidate validity and immediate-effect tokens, not authorized graph mutations.
"""
import mlx.core as mx
import mlx.nn as nn


class CellTransition(nn.Module):
    def __init__(self,input_width,hidden=128):
        super().__init__();self.hidden=hidden
        self.encode=nn.Sequential(nn.Linear(input_width,hidden),nn.GELU(),nn.Linear(hidden,128),nn.Tanh())
        self.source=nn.Linear(128,hidden)
        self.request=nn.Linear(64,hidden);self.query=nn.Linear(hidden,hidden);self.key=nn.Linear(hidden,hidden);self.value=nn.Linear(hidden,hidden)
        self.edge_score=nn.Linear(64,1);self.edge_value=nn.Linear(64,hidden)
        self.norm=nn.LayerNorm(hidden);self.mix=nn.Sequential(nn.Linear(hidden,2*hidden),nn.GELU(),nn.Linear(2*hidden,hidden))
        self.pool_query=nn.Linear(hidden,hidden);self.finish=nn.Sequential(nn.Linear(2*hidden,hidden),nn.GELU())
        self.accept=nn.Linear(hidden,1);self.successor=nn.Linear(hidden,128)

    def __call__(self,x,edges,mask,request):
        return self.transition(self.encode(x),edges,mask,request)

    def transition(self,source_tokens,edges,mask,request):
        # Generated 128-float Cell tokens enter here directly, with no field decode.
        h=self.source(source_tokens);q=self.request(request)
        scores=(self.query(h)@mx.swapaxes(self.key(h),-1,-2))/(self.hidden**.5)+self.edge_score(edges)[...,0]
        weights=mx.softmax(mx.where(mask[:,None,:],scores,-1e9),axis=-1)
        context=mx.sum(weights[...,None]*(self.value(h)[:,None,:,:]+self.edge_value(edges)),axis=2)
        h=self.norm(h+context);h=self.norm(h+self.mix(h))
        pool=mx.sum(h*self.pool_query(q)[:,None,:],axis=-1)/(self.hidden**.5)
        weights=mx.softmax(mx.where(mask,pool,-1e9),axis=-1)
        z=self.finish(mx.concatenate([mx.sum(weights[...,None]*h,axis=1),q],axis=1))
        return self.accept(z)[:,0],mx.tanh(self.successor(z))


def loss(model,batch):
    logits,token=model(batch['x'],batch['edges'],batch['mask'],batch['request'])
    matching=nn.losses.binary_cross_entropy(logits,batch['valid'],reduction='mean')
    error=mx.mean((token-batch['target'])**2,axis=1)
    completion=mx.sum(error*batch['valid'])/mx.maximum(mx.sum(batch['valid']),1)
    encoded=model.encode(batch['x'])
    source_error=mx.mean((encoded-batch['source_target'])**2,axis=-1)
    alignment=mx.sum(source_error*batch['mask'])/mx.maximum(mx.sum(batch['mask']),1)
    return matching+completion+alignment
