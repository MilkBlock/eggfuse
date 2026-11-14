import unittest
import numpy as np
import mlx.core as mx
import test_boundary_bridges as fixtures
from device_boundary_shared_context import encode
from audit_snapshot_queries import device

class LocalContext(unittest.TestCase):
    def test_excludes_assumption_only_neighbor(self):
        b,q,p,pairs=fixtures.BoundaryBridges().fixture()
        p=dict(p,local_context=True,flow_sorts=np.array([False,True]),
               port_sorts=np.array([0,1],np.int32),sorts=np.array([[0,1]],np.int32))
        b['slot_roots']=np.array([[1,2],[1,4]],np.int32)
        b['tokens'][1]=-.7
        single={k:v[:1] for k,v in b.items()}
        expected=encode(single,q,p,pairs,np)[0]
        np.testing.assert_allclose(encode(b,q,p,pairs,np)[0],expected,atol=2e-6)
        connected=dict(b,slot_roots=np.array([[1,2],[1,2]],np.int32))
        self.assertGreater(np.linalg.norm(encode(connected,q,p,pairs,np)[0]-expected),.01)
        for boundary in (b,connected):
            expected=encode(boundary,q,p,pairs,np)[0]
            scatter=dict(p,root_capacity=8,sort_capacity=2)
            np.testing.assert_allclose(encode(boundary,q,scatter,pairs,np)[0],expected,atol=2e-6)
            db,dq,dp,di=map(device,(boundary,q,scatter,pairs))
            actual=mx.compile(lambda x:encode(x,dq,dp,di,mx))(db);mx.eval(actual)
            np.testing.assert_allclose(actual[0],expected,atol=2e-6)

if __name__=='__main__':unittest.main()
