import unittest
import numpy as np
import mlx.core as mx
from device_joint_boundary_features import compile_joint,encode
from audit_snapshot_queries import device


class JointBoundaryFeatures(unittest.TestCase):
    def test_mixed_inputs_have_nonadditive_interaction(self):
        p=compile_joint(3,6,8,32);zero=np.zeros((1,8),np.float32)
        left=zero.copy();left[:,1:4]=1
        right=zero.copy();right[:,6:]=1
        mixed=encode(left+right,p,np)-encode(left,p,np)-encode(right,p,np)+encode(zero,p,np)
        self.assertGreater(float(np.linalg.norm(mixed)),.01)
        # Existing random features are not accidentally read as raw boundary input.
        unused=zero.copy();unused[:,4:6]=100
        np.testing.assert_array_equal(encode(unused,p,np),encode(zero,p,np))

    def test_fixed_layout_and_gpu(self):
        p=compile_joint(3,6,8,32);q=compile_joint(3,6,8,32)
        np.testing.assert_array_equal(p['raw_weight'],q['raw_weight'])
        x=np.random.default_rng(2).normal(size=(7,8)).astype(np.float32)
        actual=mx.compile(lambda a:encode(a,device(p),mx))(mx.array(x));mx.eval(actual)
        np.testing.assert_allclose(actual,encode(x,p,np),atol=3e-7)
        with self.assertRaises(ValueError):encode(x[:,:7],p,np)
        with self.assertRaises(ValueError):compile_joint(6,6,8)

if __name__=='__main__':unittest.main()
