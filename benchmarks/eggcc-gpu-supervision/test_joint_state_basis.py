import unittest
import numpy as np
from joint_state_basis import fit_basis,restore
from bounded_cell_readout import normalize
from boundary_cell_ridge import D


class JointBasis(unittest.TestCase):
    def test_basis_reconstructs_known_low_rank_training_span(self):
        rng=np.random.default_rng(5);a=(rng.normal(size=(20,3))@rng.normal(size=(3,80))).astype(np.float32)
        basis,s=fit_basis(a,3)
        np.testing.assert_allclose(basis.T@basis,np.eye(3),atol=1e-6)
        np.testing.assert_allclose((a@basis)@basis.T,a,atol=1e-5)
        self.assertTrue((s[:-1]>=s[1:]).all())
        with self.assertRaises(ValueError):fit_basis(a,21)

    def test_body_scale_roundtrip_preserves_boundary(self):
        value=np.arange(2*(D+4),dtype=np.float32).reshape(2,D+4);bounds=np.array([2,4],np.float32)
        np.testing.assert_array_equal(restore(normalize(value,bounds,np),bounds,np),value)

if __name__=='__main__':unittest.main()
