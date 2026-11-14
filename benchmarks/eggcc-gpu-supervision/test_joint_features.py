import unittest
import numpy as np
import mlx.core as mx
from device_joint_features import compile_projection,expand

class JointFeatures(unittest.TestCase):
    def test_gpu_fixed_projection_and_cross_input_context_interaction(self):
        w=compile_projection(5,16);np.testing.assert_array_equal(w,compile_projection(5,16))
        x=np.array([[1,0,0,0,0],[1,1,0,0,0],[1,0,0,1,0],[1,1,0,1,0]],np.float32)
        expected=expand(x,w,np)
        # Nonzero mixed finite difference shows this is not additive context.
        mixed=expected[3]-expected[2]-expected[1]+expected[0]
        self.assertGreater(np.linalg.norm(mixed[5:]),.01)
        actual=mx.compile(lambda v:expand(v,mx.array(w),mx))(mx.array(x));mx.eval(actual)
        np.testing.assert_allclose(actual,expected,atol=2e-6)

if __name__=='__main__':unittest.main()
