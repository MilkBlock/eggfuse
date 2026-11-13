import unittest
import numpy as np
import mlx.core as mx
from latent_bake_conditions import compile_conditions,energy,hints
from latent_cell_completion import decode_state
from bake_stop_features import pack,evaluate
from boundary_cell_ridge import D,B


class LatentConditions(unittest.TestCase):
    def test_folded_energies_match_explicit_decoded_ports(self):
        rng=np.random.default_rng(4);basis=rng.normal(0,.1,(D+3*B,5)).astype(np.float32);scale=np.full(D+3*B,.2,np.float32)
        plan=(np.array([0,1,1],np.float32),[(0,2),(1,2)]);form,count=compile_conditions(plan,basis,scale,2)
        z=rng.normal(size=(1,5)).astype(np.float32);decoded=decode_state(z,np.ones(1),np.array([2]),basis,scale,np)
        old=evaluate(decoded,*pack([plan]),np);actual=energy(z,form[None,:],np)
        np.testing.assert_allclose(actual,old[:,[2,7]],rtol=2e-6,atol=1e-6)
        gpu=np.array(energy(mx.array(z),mx.array(form[None,:]),mx));np.testing.assert_allclose(gpu,actual,rtol=2e-6,atol=1e-6)
        features=hints(z,form[None,:],count[None,:],np)
        np.testing.assert_allclose(np.array(hints(mx.array(z),mx.array(form[None,:]),mx.array(count[None,:]),mx)),features,atol=1e-6)
        self.assertTrue((features[:,[2,3,4,7]]<=1).all())

    def test_empty_plan_has_no_energy_or_hints(self):
        basis=np.ones((D+B,3),np.float32);form,count=compile_conditions((np.zeros(1),[]),basis,np.ones(D+B),1)
        result=hints(np.ones((1,3),np.float32),form[None,:],count[None,:],np)
        np.testing.assert_array_equal(result,np.zeros((1,8)))

if __name__=='__main__':unittest.main()
