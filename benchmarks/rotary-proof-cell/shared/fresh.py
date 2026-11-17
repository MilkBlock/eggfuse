"""New acceptance structures. Fixed generator, never part of model fitting."""
import hashlib,json
import numpy as np
from abi import *
import spec


def freeze():
    rng=np.random.default_rng(90417)
    seen={spec.shape_key(s) for s in spec.SHAPES[:10]};shapes=[]
    while len(shapes)<16:
        plan=[]
        for role in range(4,8):
            op=int(rng.integers(2));a=int(rng.integers(role));b=int(rng.integers(role)) if op else 9
            plan.append([op,a,b])
        key=spec.shape_key(plan)
        if key in seen:continue
        seen.add(key);shapes.append(plan)
    return dict(generator_seed=90417,base_shapes=10,shapes=shapes,
                sha256=hashlib.sha256(json.dumps(shapes,sort_keys=True).encode()).hexdigest())


def register(manifest):
    if len(spec.SHAPES)==10:spec.SHAPES.extend(manifest['shapes'])
    else:assert spec.SHAPES[10:]==manifest['shapes']


def cases(manifest,hard,n=2048):
    register(manifest);rng=np.random.default_rng(90817+int(hard))
    group='joint' if hard else 'seen';out=spec.sample(group,n,rng)
    out[:,0]=rng.integers(10,26,n)
    return out,spec.positions(n,rng)


def freeze_final():
    """Fresh acceptance after the first 16 shapes became inspected diagnostics."""
    dev=freeze();rng=np.random.default_rng(91917)
    seen={spec.shape_key(s) for s in spec.SHAPES[:10]+dev['shapes']};plans=[]
    while len(plans)<16:
        p=[]
        for dst in range(4,8):
            op=int(rng.integers(2));p.append([op,int(rng.integers(dst)),int(rng.integers(dst)) if op else 9])
        key=spec.shape_key(p)
        if key in seen:continue
        seen.add(key);plans.append(p)
    combined=dev['shapes']+plans
    return dict(generator_seed=91917,base_shapes=10,shapes=combined,final_ids=list(range(26,42)),
                development_shapes=16,sha256=hashlib.sha256(json.dumps(combined,sort_keys=True).encode()).hexdigest())


def final_cases(manifest,hard,n=2048):
    register(manifest);rng=np.random.default_rng(92917+int(hard));out=[];seen=set()
    while len(out)<n:
        chunk=spec.sample('joint' if hard else 'seen',n,rng);chunk[:,0]=rng.integers(26,42,n)
        for row in chunk:
            if tuple(row) not in seen:seen.add(tuple(row));out.append(row)
            if len(out)==n:break
    return np.array(out,np.int32),spec.positions(n,rng)
