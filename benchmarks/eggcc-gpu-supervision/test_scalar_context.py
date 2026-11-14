import unittest
from copy import deepcopy
import numpy as np
import mlx.core as mx
import test_boundary_bridges as bridges
from device_scalar_context import encode,compile_scalar_context
from device_boundary_context import encode as unconditioned
from audit_snapshot_queries import device
from test_completion_states import rule


class ScalarContext(unittest.TestCase):
    def fixture(self):
        a,b,p,_=bridges.BoundaryBridges().fixture()
        a['slot_roots'][1,0]=1;a['tokens'][1]*=-1
        plan=dict(base=p,consumer_slot=1,scalar_slots=np.array([1],np.int32),compatible=np.array([True]))
        numbers=(np.array([0.,3.],np.float32),np.ones(2,bool),np.array([0.],np.float32),np.ones(1,bool))
        return a,b,numbers,plan

    def test_relative_scalar_changes_information_without_changing_old_pool(self):
        a,b,n,p=self.fixture();old=unconditioned(a,b,p['base'],np)[0]
        first=encode(a,b,*n,p,np)[0];second=encode(a,b,n[0],n[1],n[2]+3,n[3],p,np)[0]
        np.testing.assert_array_equal(old,unconditioned(a,b,p['base'],np)[0])
        self.assertGreater(np.linalg.norm(first-second),.1)
        shifted=encode(a,b,n[0]+100,n[1],n[2]+100,n[3],p,np)[0]
        np.testing.assert_allclose(first,shifted,atol=1e-6)

    def test_ineligible_nan_and_sort_mismatch_are_excluded(self):
        a,b,n,p=self.fixture();a['tokens'][1]=np.nan
        valid=np.array([True,False]);out,_=encode(a,b,n[0],valid,n[2],n[3],p,np)
        self.assertTrue(np.isfinite(out).all())
        p['compatible'][:]=False
        out,count=encode(a,b,*n,p,np);np.testing.assert_array_equal(out,0);np.testing.assert_array_equal(count,0)

    def test_gpu_and_stable_id_invariance(self):
        a,b,n,p=self.fixture();expected=encode(a,b,*n,p,np)
        aa=deepcopy(a);bb=deepcopy(b);aa['slot_roots']+=4096;bb['slot_roots']+=4096
        np.testing.assert_array_equal(encode(aa,bb,*n,p,np)[0],expected[0])
        da,db,dn,dp=map(device,(a,b,n,p))
        actual=mx.compile(lambda x:encode(x,db,*dn,dp,mx))(da);mx.eval(actual)
        for x,y in zip(actual,expected):np.testing.assert_allclose(x,y,atol=2e-6)

    def test_compiler_explicitly_rejects_uncovered_scalar_layout(self):
        r=rule(2);r['slots'].append(dict(definition='query',sort=dict(kind='i64',name='i64')))
        p=compile_scalar_context(dict(rules=[r]),0,3);self.assertEqual(p['consumer_slot'],2)
        r['slots'].append(dict(definition='query',sort=dict(kind='i64',name='i64')))
        with self.assertRaises(ValueError):compile_scalar_context(dict(rules=[r]),0,4)

if __name__=='__main__':unittest.main()
