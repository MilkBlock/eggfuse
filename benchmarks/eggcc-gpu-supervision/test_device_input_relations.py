import unittest
from copy import deepcopy
import numpy as np
import mlx.core as mx
from device_input_relations import encode,projection


class InputRelations(unittest.TestCase):
    def fixture(self):
        rng=np.random.default_rng(1)
        return dict(sources=np.array([[1,1,2,9]]),generations=np.zeros((1,4),np.int32),
            ports=np.array([[0,1,0,0]]),roots=np.array([[7,8,7,7]]),sorts=np.array([0,0,0,0]),
            valid=np.array([[True,True,True,False]]),tokens=rng.normal(size=(1,4,128)).astype(np.float32),
            roles=rng.normal(size=(1,4,128)).astype(np.float32))

    def test_source_and_equality_are_distinct_and_generation_matters(self):
        x=self.fixture();w=projection();base,count=encode(x,w,np)
        self.assertEqual(count.tolist(),[[1,0,1,1]])
        y=deepcopy(x);y['generations'][0,1]=1
        self.assertEqual(encode(y,w,np)[1].tolist(),[[0,0,1,1]])
        y=deepcopy(x);y['sorts'][2]=1
        self.assertEqual(encode(y,w,np)[1].tolist(),[[1,0,0,0]])
        self.assertFalse(np.array_equal(base,encode(y,w,np)[0]))

    def test_renaming_and_padding_invariance(self):
        x=self.fixture();w=projection();a=encode(x,w,np)[0]
        x['sources']=100-x['sources'];x['roots']=900-x['roots']
        x['tokens'][0,3]=np.nan;x['roles'][0,3]=np.nan
        np.testing.assert_array_equal(a,encode(x,w,np)[0])
        self.assertTrue(np.isfinite(a).all())

    def test_fixed_gpu_dataflow_matches_cpu(self):
        x=self.fixture();w=projection();expected,count=encode(x,w,np)
        actual,n=mx.compile(lambda y:encode(y,mx.array(w),mx))({k:mx.array(v) for k,v in x.items()})
        mx.eval(actual,n)
        np.testing.assert_allclose(np.array(actual),expected,atol=2e-6)
        np.testing.assert_array_equal(np.array(n),count)

if __name__=='__main__':unittest.main()
