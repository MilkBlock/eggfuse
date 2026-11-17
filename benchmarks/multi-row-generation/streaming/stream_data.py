"""Offline held-out right-multiplicity families; no inference dependencies."""
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'allocation'))
from data import generate,features,truth,Q,fingerprint
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'coverage'))
from fixtures import fresh as coverage_fresh


def fresh(count,seed,family,forbidden=()):
    if family=='triple_right':d=generate(count,seed,True)
    elif family=='four_right':d=coverage_fresh(count,seed,'four_left')
    else:raise ValueError(family)
    a=d['b'].copy();b=d['a'].copy();assert not {fingerprint(x,y) for x,y in zip(a,b)}&set(forbidden)
    targets=np.zeros((count,Q,6),np.int32)
    for g in range(count):
        for i,record in enumerate(truth(a[g],b[g])):targets[g,i]=[1,*record]
    return dict(a=a,b=b,x=features(a,b),targets=targets)
