import unittest
import numpy as np
from fit_completion_classifier import balanced_state_weights,fit_head

class BalancedRidge(unittest.TestCase):
    def test_weights_and_closed_form(self):
        rng=np.random.default_rng(41);x=rng.normal(size=(8,3)).astype(np.float32)
        y=np.eye(3,dtype=np.float32)[[0,0,0,0,0,1,1,2]];w=balanced_state_weights(y)
        np.testing.assert_allclose(w@y,np.full(3,8/3),rtol=1e-6)
        h=fit_head(x,y,10.,weights=w);z=((x-h['mean'])/h['scale']).astype(np.float64);ww=w/w.mean()
        primal=np.linalg.solve(z.T@(ww[:,None]*z)+10*np.eye(3),z.T@(ww[:,None]*(y-h['bias'])))
        np.testing.assert_allclose(h['coef'],primal,atol=1e-6)
        self.assertTrue(all(v.dtype==np.float32 for v in h.values()))
        with self.assertRaises(ValueError):fit_head(x,y,weights=np.zeros(8))
        with self.assertRaises(ValueError):balanced_state_weights(np.zeros((2,3)))

if __name__=='__main__':unittest.main()
