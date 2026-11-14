"""Exact input collisions in bounded synthetic continuation samples.

Uses reference source tokens, not predicted recurrent tokens. No rounding is
applied: near-collisions and numerical conditioning require separate checks.
"""
import hashlib
import numpy as np


def audit(data):
    data=dict(data)
    # Boundary tokens are recomputed from seed_x; owned tokens bypass seed_x.
    # Do not let unused teacher values spuriously distinguish model inputs.
    data['tokens']=np.where(data['replace'][...,None],data['tokens'],0)
    data['seed_x']=np.where(data['replace'][...,None],0,data['seed_x'])
    fields=['tokens','seed_x','edges','mask','replace','request']
    if 'relations' in data:fields.append('relations')
    groups={};conflicts=[];duplicates=0
    for i in range(len(data['valid'])):
        digest=hashlib.sha256()
        for key in fields:
            value=np.ascontiguousarray(data[key][i])
            digest.update(key.encode());digest.update(str((value.shape,value.dtype)).encode());digest.update(value.tobytes())
        signature=digest.digest()
        previous=groups.setdefault(signature,[])
        for j in previous:
            # Confirm exact bytes as well as the hash before reporting a collision.
            if not all(data[k][i].tobytes()==data[k][j].tobytes() for k in fields):continue
            mismatch=bool(data['valid'][i])!=bool(data['valid'][j])
            if data['valid'][i] and data['valid'][j]:
                common=data['eq_mask'][i]&data['eq_mask'][j]
                mismatch |= bool(np.any(data['eq_target'][i][common]!=data['eq_target'][j][common]))
            if mismatch:
                conflicts.append([int(j),int(i)])
                break
        if previous:duplicates+=1
        previous.append(i)
    return dict(samples=len(data['valid']),unique_inputs=len(groups),duplicate_inputs=duplicates,
                conflicting_samples=len(conflicts),examples=conflicts[:20],input_fields=fields,
                scope='exact reference-token input collisions against validity and overlapping Eq labels; not near-collisions or recurrent closure')
