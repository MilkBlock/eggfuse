"""Compile positive owner relations into a dense input for new target tokens.

This code carries proof features, not an exact identity or proof certificate.
The learned target residual must still pass full semantic audits. Source tokens
remain immutable; no oracle output or runtime representative enters compilation.
"""
from functools import lru_cache
import numpy as np
from multi_entry_ridge import vec


@lru_cache(maxsize=None)
def basis(width):
    pairs=list(zip(*np.triu_indices(width,1)))
    names=[(side,int(i),int(j)) for side in ('source','target') for i,j in pairs]
    names += [('cross',i,j) for i in range(width) for j in range(width)]
    return np.array([vec(('owner-proven-eq',)+name) for name in names],np.float32)


def encode(known,source_request,target_request,width):
    bits=np.concatenate([known[k] for k in ('source_known_eq','target_known_eq','cross_known_eq')]).astype(np.float32)
    if bits.shape!=(len(basis(width)),):raise ValueError('owner proof layout mismatch')
    raw=bits@basis(width)/np.sqrt(max(float(bits.sum()),1.))
    return np.tanh(raw+source_request+target_request).astype(np.float32)


def key(source,target,owner):
    return source.tobytes()+target.tobytes()+owner.tobytes()


def enrich(data,*catalogs):
    """Upgrade saved replay from static compiler catalogs, never label columns.

    Both train/test template definitions are permitted compiler inputs. Their
    instance truth and teacher tokens are not read. Conflicting descriptors or
    unknown catalog entries fail instead of silently using an empty feature.
    """
    lookup={}
    for cat in catalogs:
        for i in np.flatnonzero(cat['valid']>0):
            k=key(cat['source_request'][i],cat['request'][i],cat['owner_request'][i]);v=cat['owner_proof_code'][i]
            if k in lookup and not np.array_equal(lookup[k],v):raise ValueError('ambiguous static owner descriptor')
            lookup[k]=v
    codes=np.array([lookup[key(s,t,o)] for s,t,o in zip(data['c_source_request'],data['c_request'],data['c_owner_request'])])
    if 'c_owner_proof_code' in data and not np.array_equal(data['c_owner_proof_code'],codes):raise ValueError('replay proof differs from compiler')
    return dict(data,c_owner_proof_code=codes)
