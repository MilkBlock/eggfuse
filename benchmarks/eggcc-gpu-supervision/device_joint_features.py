"""Fixed nonlinear mixing of input and boundary columns; no learned encoder."""
import numpy as np


def compile_projection(width,hidden=256):
    if width<1 or hidden<1:raise ValueError('positive joint feature dimensions')
    return np.random.default_rng(20261114).normal(0,1/np.sqrt(width),(width,hidden)).astype(np.float32)


def expand(x,projection,xp):
    return xp.concatenate([x,xp.tanh(x@projection)],axis=1)
