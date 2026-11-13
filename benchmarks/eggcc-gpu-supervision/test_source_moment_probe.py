import unittest
import numpy as np
import mlx.core as mx
from source_moment_probe import moment, matrix

class MomentTests(unittest.TestCase):
    def test_cancellation_and_padding(self):
        x=np.array([[[1.,2.],[-1.,-2.],[999.,999.]]],np.float32)
        valid=np.array([[True,True,False]])
        np.testing.assert_array_equal(moment(x,valid,np),[[1.,4.]])
        np.testing.assert_array_equal(moment(x,~np.ones_like(valid),np),[[0.,0.]])
        perm=[2,0,1]
        np.testing.assert_array_equal(moment(x[:,perm],valid[:,perm],np),moment(x,valid,np))

    def test_interactions_do_not_read_completion_labels(self):
        node=dict(seed=np.ones(128,np.float32)*.2,q=np.zeros(256,np.float32),
                  target=np.ones(128,np.float32),edges=[(0,np.ones(128,np.float32))],
                  edge_routes=[np.ones(4,np.float32)],edge_width=512)
        states=np.ones((1,128),np.float32)*.3
        w=np.zeros((1408,256),np.float32)
        first=matrix([node],states,w,'seed_source_quadratics')
        node['target'][:]=999
        np.testing.assert_array_equal(first,matrix([node],states,w,'seed_source_quadratics'))
        np.testing.assert_allclose(first[:,-256:-128],.012,atol=1e-7)
        np.testing.assert_allclose(first[:,-128:],.018,atol=1e-7)

    def test_gpu(self):
        x=np.random.default_rng(9).normal(size=(3,7,128)).astype(np.float32)
        valid=np.random.default_rng(10).random((3,7))>.3
        got=mx.compile(lambda x,v:moment(x,v,mx))(mx.array(x),mx.array(valid));mx.eval(got)
        np.testing.assert_allclose(np.array(got),moment(x,valid,np),atol=2e-6)

if __name__=='__main__':unittest.main()
