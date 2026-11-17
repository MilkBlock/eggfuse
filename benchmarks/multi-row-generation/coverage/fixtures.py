"""Offline new multiplicity families; no model or GPU dependencies."""
import sys
from pathlib import Path
from collections import Counter
from itertools import combinations_with_replacement
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'allocation'))
from data import K,V,N,Q,features,truth,fingerprint,shape


def fresh(count,seed,family,forbidden=()):
    multisets=list(combinations_with_replacement(range(6),N));banks={}
    for a in multisets:
        ca=Counter(a)
        if max(ca.values())!=(3 if family=='double_triple' else 4):continue
        for b in multisets:
            cb=Counter(b)
            if family=='double_triple':
                if max(cb.values())!=3:continue
            elif family=='four_left':
                if max(cb.values())>2:continue
            else:raise ValueError(family)
            count_matches=sum(ca[k]*cb[k] for k in ca)
            if count_matches>Q:continue
            banks.setdefault(count_matches,[]).append((a,b))
    cardinalities=sorted(banks);rng=np.random.default_rng(seed);seen=set(forbidden);aa=[];bb=[]
    while len(aa)<count:
        choices=banks[cardinalities[len(aa)%len(cardinalities)]];a,b=choices[int(rng.integers(len(choices)))];keys=rng.permutation(K)
        a=np.stack((keys[np.array(a)][rng.permutation(N)],rng.integers(V,size=N)),-1).astype(np.int32)
        b=np.stack((keys[np.array(b)][rng.permutation(N)],rng.integers(V,size=N)),-1).astype(np.int32)
        fp=fingerprint(a,b)
        if fp in seen:continue
        seen.add(fp);aa.append(a);bb.append(b)
    aa=np.array(aa);bb=np.array(bb);targets=np.zeros((count,Q,6),np.int32)
    for g in range(count):
        for t,record in enumerate(truth(aa[g],bb[g])):targets[g,t]=[1,*record]
    return dict(a=aa,b=bb,x=features(aa,bb),targets=targets)
