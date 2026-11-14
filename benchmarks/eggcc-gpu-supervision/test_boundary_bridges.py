import unittest
import numpy as np
import mlx.core as mx
from device_boundary_bridges import compile_pairs,encode
from device_boundary_context import encode as marginals
from audit_snapshot_queries import device


class BoundaryBridges(unittest.TestCase):
    def fixture(self):
        plan=dict(ports=np.array([0,1],np.int32),port_sorts=np.zeros(2,np.int32),sorts=np.zeros((1,2),np.int32),roles=np.random.default_rng(7).normal(size=(1,2,64)).astype(np.float32),width=2,
            token_weight=np.full((128,3),.01,np.float32),role_weight=np.random.default_rng(8).normal(0,.1,size=(64,3)).astype(np.float32))
        boundary=dict(rule=np.zeros(2,np.int32),slot_roots=np.array([[1,2],[3,4]],np.int32),slot_valid=np.ones((2,2),bool),live=np.ones(2,bool),tokens=np.ones((2,128),np.float32))
        bindings=dict(slot_roots=np.array([[1,2]],np.int32),slot_valid=np.ones((1,2),bool),live=np.ones(1,bool),witness_rows=np.empty((1,0),np.int32))
        return boundary,bindings,plan,compile_pairs(plan)

    def test_distinguishes_same_marginals_but_different_shared_cell(self):
        a,b,p,pairs=self.fixture();separate=dict(a,slot_roots=np.array([[1,4],[3,2]],np.int32))
        np.testing.assert_array_equal(marginals(a,b,p,np)[0],marginals(separate,b,p,np)[0])
        together,count=encode(a,b,p,pairs,np);apart,other=encode(separate,b,p,pairs,np)
        self.assertGreater(np.linalg.norm(together),.1);np.testing.assert_array_equal(apart,0)
        np.testing.assert_array_equal(count,1);np.testing.assert_array_equal(other,0)

    def test_ineligible_nan_neighbor_is_excluded(self):
        a,b,p,pairs=self.fixture();a['live'][0]=False;a['tokens'][0]=np.nan
        out,counts=encode(a,b,p,pairs,np)
        self.assertTrue(np.isfinite(out).all());np.testing.assert_array_equal(out,0);np.testing.assert_array_equal(counts,0)

    def test_gpu_and_id_renaming_invariance(self):
        a,b,p,pairs=self.fixture();expected=encode(a,b,p,pairs,np)
        shifted=dict(a,slot_roots=a['slot_roots']+1000);bb=dict(b,slot_roots=b['slot_roots']+1000)
        np.testing.assert_array_equal(encode(shifted,bb,p,pairs,np)[0],expected[0])
        da,db,dp,dq=map(device,(a,b,p,pairs))
        actual=mx.compile(lambda x:encode(x,db,dp,dq,mx))(da);mx.eval(actual)
        for x,y in zip(actual,expected):np.testing.assert_allclose(np.array(x),y,atol=2e-6)

if __name__=='__main__':unittest.main()
