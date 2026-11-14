import unittest
import numpy as np
import mlx.core as mx
import test_boundary_bridges as fixtures
from device_boundary_shared_context import encode
from audit_snapshot_queries import device

class MeanContext(unittest.TestCase):
    def test_uniform_replication_and_gpu_parity(self):
        b,q,p,pairs=fixtures.BoundaryBridges().fixture();p=dict(p,mean_context=True)
        replicated={k:np.concatenate([v,v,v],axis=0) for k,v in b.items()}
        expected=encode(b,q,p,pairs,np)[0]
        np.testing.assert_allclose(encode(replicated,q,p,pairs,np)[0],expected,atol=2e-6)
        db,dq,dp,di=map(device,(replicated,q,dict(p,root_capacity=8,sort_capacity=1),pairs))
        actual=mx.compile(lambda x:encode(x,dq,dp,di,mx))(db);mx.eval(actual)
        np.testing.assert_allclose(actual[0],expected,atol=2e-6)

if __name__=='__main__':unittest.main()
