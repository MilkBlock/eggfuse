import unittest
import numpy as np
import mlx.core as mx
from boundary_cell_ridge import D,B
from bounded_cell_readout import normalize,preactivation,decode


class BoundedReadout(unittest.TestCase):
    def test_inverse_target_and_both_channel_scales(self):
        bounds=np.array([2,8],np.float32)
        unit=np.random.default_rng(4).uniform(-.9,.9,(2,D+B)).astype(np.float32)
        target=unit.copy();target[:,:D]*=bounds[:,None]
        np.testing.assert_allclose(normalize(target,bounds,np),unit,atol=1e-7)
        raw=preactivation(target,bounds)
        np.testing.assert_allclose(decode(raw,bounds,np),target,atol=1e-6)
        np.testing.assert_allclose(np.array(decode(mx.array(raw),mx.array(bounds),mx)),target,atol=1e-6)

    def test_saturated_teacher_has_finite_inverse_and_declared_bias(self):
        bounds=np.array([3],np.float32);target=np.ones((1,D+B),np.float32);target[:,:D]*=3
        raw=preactivation(target,bounds)
        self.assertTrue(np.isfinite(raw).all())
        recovered=decode(raw,bounds,np)
        np.testing.assert_allclose(recovered,target*.9999,atol=1e-6)

    def test_finite_extreme_readout_preserves_ranges(self):
        raw=np.full((1,D+B),1e20,np.float32);raw[:,::2]*=-1
        output=decode(raw,np.array([4],np.float32),np)
        self.assertTrue(np.isfinite(output).all())
        self.assertTrue((np.abs(output[:,:D])<=4).all())
        self.assertTrue((np.abs(output[:,D:])<=1).all())

    def test_invalid_teacher_range_is_rejected(self):
        target=np.zeros((1,D+B),np.float32);target[0,D]=1.1
        with self.assertRaises(ValueError):preactivation(target,np.array([1],np.float32))

if __name__=='__main__':unittest.main()
