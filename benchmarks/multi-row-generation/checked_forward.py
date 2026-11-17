"""Readout-bound GPU verification: checks NN proposals, never repairs them."""
import mlx.core as mx
from task import KEYS
from verify import fields_from_logits


def check(a,b,out,coords_b,coords_pair,decoder_weight,decoder_bias):
    batch,n=a.shape[:2]
    keys_valid=mx.all((a[:,:,0]>=0)&(a[:,:,0]<KEYS),-1)&mx.all((b[:,:,:2]>=0)&(b[:,:,:2]<KEYS),axis=(1,2))
    counts=mx.zeros((batch,KEYS),mx.int32)
    graph=mx.broadcast_to(mx.arange(batch)[:,None],(batch,n))
    counts=counts.at[graph,mx.clip(a[:,:,0],0,KEYS-1)].add(mx.ones((batch,n),mx.int32))
    unique=mx.all(counts<=1,-1)
    covered=mx.all(mx.sort(a[:,:,0],axis=-1)==mx.sort(b[:,:,0],axis=-1),-1)
    # Membership only: no key->matching-row map or correct output pointer is built.
    next_present=mx.all(mx.take_along_axis(counts,mx.clip(b[:,:,1],0,KEYS-1),axis=1)>0,-1)
    scope=keys_valid&unique&covered&next_present
    scores=out['latent']@mx.swapaxes(decoder_weight,-1,-2)+decoder_bias
    fields=fields_from_logits(scores);advertised=fields_from_logits(out['field_logits'])
    bound=mx.all(fields==advertised,-1)
    p=out['pointers'];inside=(p>=0)&(p<n);idx=mx.clip(p,0,n-1)
    picked=mx.take_along_axis(b,idx[0,...,None],axis=1)
    wanted=mx.stack((a[:,:,0],picked[:,:,1],a[:,:,1],picked[:,:,2]),-1)
    valid1=inside[0]&bound[0]&scope[:,None]&(a[:,:,0]==picked[:,:,0])&mx.all(fields[0]==wanted,-1)
    valid1 &= mx.all(out['addresses'][0]==coords_b[idx[0]],-1)
    neighbor=mx.take_along_axis(fields[0],idx[1,...,None],axis=1)
    neighbor_valid=mx.take_along_axis(valid1,idx[1],axis=1)
    wanted2=mx.stack((fields[0,:,:,0],neighbor[:,:,1],fields[0,:,:,2],neighbor[:,:,3]),-1)
    valid2=inside[1]&bound[1]&valid1&neighbor_valid&(fields[0,:,:,1]==neighbor[:,:,0])&mx.all(fields[1]==wanted2,-1)
    valid2 &= mx.all(out['addresses'][1]==coords_pair[idx[1]],-1)
    valid=mx.stack((valid1,valid2))
    return dict(scope=scope,latent_bound=bound,valid=valid,whole_graph=mx.all(valid1&valid2,-1))
