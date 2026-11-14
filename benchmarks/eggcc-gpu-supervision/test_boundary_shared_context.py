import unittest
import numpy as np
import mlx.core as mx
from device_boundary_shared_context import encode
from test_boundary_bridges import BoundaryBridges
from audit_snapshot_queries import device

class SharedContext(unittest.TestCase):
    def test_gpu_renaming_and_retired_nan(self):
        a,b,p,pairs=BoundaryBridges().fixture()
        expected=encode(a,b,p,pairs,np)
        shifted=dict(a,slot_roots=a['slot_roots']+100)
        bb=dict(b,slot_roots=b['slot_roots']+100)
        np.testing.assert_array_equal(encode(shifted,bb,p,pairs,np)[0],expected[0])
        da,db,dp,dq=map(device,(a,b,p,pairs))
        result=mx.compile(lambda x:encode(x,db,dp,dq,mx))(da);mx.eval(result)
        for x,y in zip(result,expected):np.testing.assert_allclose(np.array(x),y,atol=2e-6)
        a['live'][:]=False;a['tokens'][:]=np.nan
        out,count=encode(a,b,p,pairs,np)
        np.testing.assert_array_equal(out,0);np.testing.assert_array_equal(count,0)

if __name__=='__main__':unittest.main()
