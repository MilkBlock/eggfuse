import unittest
import numpy as np
import mlx.core as mx
from neural_snapshot_candidates import relational_edges


class RelationalEdges(unittest.TestCase):
    def test_float_matrix_reduction_matches_dense_reference(self):
        rng=np.random.default_rng(231)
        labels=rng.integers(-1,7,size=(9,22),dtype=np.int32)
        labels[0]=-1
        roles=np.tanh(rng.normal(size=(9,22,64))).astype(np.float32)
        sources=rng.integers(0,9,size=(17,4),dtype=np.int32)
        sources[0]=0
        expected=np.zeros((17,4,4,64),np.float32)
        for a in range(4):
            for b in range(4):
                x,y=labels[sources[:,a]],labels[sources[:,b]]
                same=(x[:,:,None]==y[:,None,:])&(x[:,:,None]>=0)&(y[:,None,:]>=0)
                product=roles[sources[:,a]][:,:,None,:]*roles[sources[:,b]][:,None,:,:]
                expected[:,a,b]=(same[:,:,:,None]*product).sum((1,2))/np.sqrt(np.maximum(same.sum((1,2)),1))[:,None]
        actual=mx.compile(relational_edges)(mx.array(labels),mx.array(roles),mx.array(sources));mx.eval(actual)
        np.testing.assert_allclose(actual,expected,atol=2e-5,rtol=2e-5)
        np.testing.assert_array_equal(np.array(actual)[0],0)


if __name__=='__main__':unittest.main()
