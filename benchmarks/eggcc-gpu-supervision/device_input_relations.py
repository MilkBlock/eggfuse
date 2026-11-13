"""Input-only selected-witness features; fixed floating dataflow, no gradients.

IDs determine typed connectivity only. No target token, RHS result, physical
owner address, or future equivalence is an input. These experimental columns
are not installed in the resident ridge until held-out semantic validation.
"""
import numpy as np


def projection(width=32):
    return np.random.default_rng(20261115).normal(0, 1/np.sqrt(128), (128,width)).astype(np.float32)


def inputs(recipe,capture):
    c=capture;r=c['request'];b=c['bindings'];ports=np.asarray(c['input_ports'],int)
    rule=recipe['rules'][int(c['rule'])]
    names=sorted({s['sort']['name'] for s in rule['slots'] if s['sort']['kind']=='eq'})
    sorts=np.array([names.index(rule['slots'][p]['sort']['name']) for p in ports],np.int32)
    return dict(sources=r['sources'],generations=r['generations'],ports=c['source_ports'],
        roots=b['slot_roots'][:,ports],sorts=sorts,
        valid=r['edge_valid'] & b['slot_valid'][:,ports],tokens=c['source_tokens'],roles=r['edge'])


def relations(x,xp):
    valid=x['valid'];n=valid.shape[-1]
    pair=valid[:,:,None]&valid[:,None,:]&(xp.arange(n)[:,None]<xp.arange(n)[None,:])
    source=(x['sources'][:,:,None]==x['sources'][:,None,:]) & (x['generations'][:,:,None]==x['generations'][:,None,:])
    port=source & (x['ports'][:,:,None]==x['ports'][:,None,:])
    eq=(x['roots'][:,:,None]==x['roots'][:,None,:]) & (x['sorts'][:,None]==x['sorts'][None,:])
    # Same source is NOT the same fact as equal input values. Keep both.
    return xp.stack([pair&source,pair&port,pair&eq,pair&eq&~source],axis=1)


def encode(x,weight,xp):
    masks=relations(x,xp)
    # Padding (including NaN padding) must not enter any floating product.
    t=xp.where(x['valid'][:,:,None],x['tokens'],0)
    r=xp.where(x['valid'][:,:,None],x['roles'],0)
    h=xp.tanh((t*r)@weight)
    joined=masks.astype(xp.float32)@h[:,None,:,:]
    count=xp.sum(masks,axis=(-2,-1))
    sums=xp.sum(h[:,None,:,:]*joined,axis=-2)
    out=xp.tanh(sums/xp.sqrt(xp.maximum(count,1).astype(xp.float32))[:,:,None])
    return out.reshape(out.shape[0],-1),count
