import unittest
import numpy as np
import mlx.core as mx
from device_eq_completion import merge_round


def dense(roots,sorts,pairs,active):
    n=len(roots);safe=np.clip(pairs,0,n-1);within=np.all((pairs>=0)&(pairs<n),axis=1)
    typed=(sorts[safe[:,0]]==sorts[safe[:,1]])&(sorts[safe[:,0]]>=0)
    sr=np.clip(roots,0,n-1);valid=np.all((roots>=0)&(roots<n)&(roots<=np.arange(n)))&np.all(sorts==sorts[sr])
    allowed=active&within&typed&valid;ends=sr[safe];small=np.min(ends,axis=1);labels=np.arange(n,dtype=roots.dtype)
    touching=(labels[:,None]==ends[:,0])|(labels[:,None]==ends[:,1]);mapping=np.min(np.where(touching&allowed,small,labels[:,None]),axis=1)
    updated=mapping[sr];updated=updated[updated]
    return np.where(valid,updated,roots),np.any(active&~(within&typed))|~valid

class ScatterEq(unittest.TestCase):
    def test_dense_equivalence_and_device_parity(self):
        rng=np.random.default_rng(8)
        for mode in range(12):
            n=19;roots=np.arange(n,dtype=np.int32);sorts=np.zeros(n,np.int32)
            roots[5:9]=4
            if mode%3==0:sorts[10:]=1
            if mode%4==0:roots[1]=n+2
            pairs=rng.integers(-2,n+2,size=(100,2),dtype=np.int32);active=rng.random(100)>.2
            expected=dense(roots,sorts,pairs,active)
            for a,b in zip(merge_round(roots,sorts,pairs,active,np),expected):np.testing.assert_array_equal(a,b)
            result=mx.compile(lambda r,s,p,a:merge_round(r,s,p,a,mx))(*map(mx.array,(roots,sorts,pairs,active)));mx.eval(result)
            for a,b in zip(result,expected):np.testing.assert_array_equal(a,b)

if __name__=='__main__':unittest.main()
