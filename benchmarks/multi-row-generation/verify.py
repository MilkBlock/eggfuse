"""Device-side checking of supplied neural bindings; no matching or answer repair."""
import mlx.core as mx
from task import KEYS,VALUES


def fields_from_logits(logits):
    fields=[];start=0
    for width in (KEYS,KEYS,VALUES,VALUES):
        fields.append(mx.argmax(logits[...,start:start+width],-1));start+=width
    return mx.stack(fields,-1)


def verify(a,b,result,coords_b,coords_pair):
    # This finite-family scope check sorts keys, not their matching bindings.
    ka=mx.sort(a[:,:,0],axis=-1);kb=mx.sort(b[:,:,0],axis=-1)
    unique=mx.all(ka[:,1:]!=ka[:,:-1],axis=-1)&mx.all(kb[:,1:]!=kb[:,:-1],axis=-1)
    covered=mx.all(ka==kb,axis=-1)
    next_covered=mx.all(mx.any(b[:,:,1,None]==a[:,None,:,0],axis=-1),axis=-1)
    scope=unique&covered&next_covered
    p=result['pointers'];f=fields_from_logits(result['field_logits']);n=a.shape[1]
    good_range=(p>=0)&(p<n);idx=mx.clip(p,0,n-1)
    picked_b=mx.take_along_axis(b,idx[0,...,None],axis=1)
    expected1=mx.stack((a[:,:,0],picked_b[:,:,1],a[:,:,1],picked_b[:,:,2]),-1)
    valid1=good_range[0]&(a[:,:,0]==picked_b[:,:,0])&mx.all(f[0]==expected1,-1)
    valid1 &= mx.all(result['addresses'][0]==coords_b[idx[0]],-1)&scope[:,None]
    partner=mx.take_along_axis(f[0],idx[1,...,None],axis=1)
    partner_valid=mx.take_along_axis(valid1,idx[1],axis=1)
    expected2=mx.stack((f[0,:,:,0],partner[:,:,1],f[0,:,:,2],partner[:,:,3]),-1)
    valid2=good_range[1]&valid1&partner_valid&(f[0,:,:,1]==partner[:,:,0])&mx.all(f[1]==expected2,-1)
    valid2 &= mx.all(result['addresses'][1]==coords_pair[idx[1]],-1)
    return dict(scope=scope,valid=mx.stack((valid1,valid2)),whole_graph=mx.all(valid1&valid2,-1))
