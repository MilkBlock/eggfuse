"""Dense current-context port features; exact handles define incidence only.

No predicted latent, raw identity magnitude or CPU target enters these features.
Context extraction is charged work, not a demonstrated fast GPU implementation.
"""
import numpy as np


def port_context(bank, entry_roots, xp=np):
    roots=xp.array(bank['roots']).reshape(-1)
    roles=xp.array(bank['roles']).reshape(-1,64)
    valid=(xp.array(bank['mask'])[:,None]&xp.array(bank['slot_valid'])).reshape(-1)
    query=xp.array(entry_roots)
    same=(query[...,None]==roots)&(query[...,None]>=0)&valid
    messages=same.astype(roles.dtype)@roles
    counts=xp.sum(same,axis=-1)
    return xp.tanh(messages/xp.sqrt(xp.maximum(counts,1))[...,None])
