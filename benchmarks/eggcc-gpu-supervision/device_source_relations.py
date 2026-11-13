"""Pairwise source-sharing features; integer identities only define connectivity.

Fixed batched floating matmul, products and tanh; no learned gradients. Inputs
are established continuation edges, not predicted or future consumer results.
"""
def encode(sources, coefficients, valid, xp):
    width=sources.shape[-1]
    if coefficients.shape[:-1]!=sources.shape or valid.shape!=sources.shape:
        raise ValueError('source relation shape mismatch')
    same=sources[..., :,None]==sources[...,None,:]
    earlier=xp.arange(width)[:,None]<xp.arange(width)[None,:]
    pairs=same&earlier&valid[..., :,None]&valid[...,None,:]
    values=xp.where(valid[...,None],coefficients,0)
    joined=xp.matmul(pairs.astype(xp.float32),values)
    count=xp.sum(pairs,axis=(-2,-1))
    return xp.tanh(xp.sum(values*joined,axis=-2)/xp.sqrt(xp.maximum(count,1))[...,None])
