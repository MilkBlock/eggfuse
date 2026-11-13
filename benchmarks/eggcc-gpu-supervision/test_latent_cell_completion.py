import unittest
import numpy as np
import mlx.core as mx
from latent_cell_completion import compile_attachment,decode_state,feature
from corpus_cell_ridge import initial_attachment
from boundary_cell_ridge import D,B


class LatentCompletion(unittest.TestCase):
    def test_folded_attachment_equals_decoding_without_full_runtime_state(self):
        rng=np.random.default_rng(12);basis=rng.normal(size=(D+2*B,7)).astype(np.float32);scale=np.linspace(.1,.5,D+2*B,dtype=np.float32)
        ports=[('input',0),('input',1)];binding=[(0,ports[0]),(2,ports[1]),(5,ports[0])]
        z=rng.normal(size=(2,7)).astype(np.float32);bounds=np.array([2,3],np.float32);gains=np.array([1,4],np.float32)
        p=np.stack([compile_attachment(ports,binding,basis,scale,g) for g in gains]);decoded=decode_state(z,bounds,gains,basis,scale,np)
        expected=np.stack([initial_attachment(v,ports,binding) for v in decoded]);actual=(z[:,None,:]@p)[:,0,:]
        np.testing.assert_allclose(actual,expected,rtol=2e-6,atol=2e-5)
        np.testing.assert_allclose(np.array((mx.array(z)[:,None,:]@mx.array(p))[:,0,:]),expected,rtol=2e-6,atol=2e-5)
        np.testing.assert_array_equal(compile_attachment(ports,[],basis,scale,1),np.zeros((7,D),np.float32))

    def test_latent_features_bounded_and_backend_agrees(self):
        rng=np.random.default_rng(2);z=rng.normal(size=(2,7)).astype(np.float32)*1e3;q=np.zeros((2,D),np.float32);p=rng.normal(size=(2,7,D)).astype(np.float32);w=rng.normal(size=(7+4*D,11)).astype(np.float32)
        expected=feature(z,q,q,p,w,np);actual=feature(mx.array(z),mx.array(q),mx.array(q),mx.array(p),mx.array(w),mx)
        self.assertTrue(np.isfinite(expected).all());self.assertTrue((np.abs(expected)<=1).all())
        np.testing.assert_allclose(np.array(actual),expected,atol=2e-5)

if __name__=='__main__':unittest.main()
