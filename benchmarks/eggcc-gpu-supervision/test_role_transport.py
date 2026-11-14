import unittest
import numpy as np
import mlx.core as mx
from test_boundary_bridges import BoundaryBridges
from audit_snapshot_queries import device
from device_boundary_shared_context import encode, with_role_transport

class RoleTransport(unittest.TestCase):
    def test_baked_gate_gpu_parity_and_typed_renaming(self):
        a,b,p,pairs=BoundaryBridges().fixture()
        p=with_role_transport(p)
        np.testing.assert_array_equal(p['transport_gate'],np.tanh(p['roles']@p['role_weight']))
        expected=encode(a,b,p,pairs,np)[0]
        self.assertFalse(np.allclose(expected,encode(a,b,dict(p,role_transport=False),pairs,np)[0]))
        renamed=encode(dict(a,slot_roots=a['slot_roots']+100),dict(b,slot_roots=b['slot_roots']+100),p,pairs,np)[0]
        np.testing.assert_array_equal(renamed,expected)
        bounded=dict(p,root_capacity=8,sort_capacity=1)
        np.testing.assert_allclose(encode(a,b,bounded,pairs,np)[0],expected,atol=2e-6)
        da,db,dp,dq=map(device,(a,b,bounded,pairs))
        result=mx.compile(lambda x:encode(x,db,dp,dq,mx))(da);mx.eval(result)
        np.testing.assert_allclose(result[0],expected,atol=2e-6)
        a['live'][:]=False;a['tokens'][:]=np.nan
        np.testing.assert_array_equal(encode(a,b,p,pairs,np)[0],0)

if __name__=='__main__':unittest.main()
