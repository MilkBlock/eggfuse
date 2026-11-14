import unittest
from copy import deepcopy
import numpy as np
import mlx.core as mx
from test_device_join_transition import fixture
from test_device_query_join import fixture as recipe_fixture
from device_query_join import match
from device_boundary_context import compile_context,snapshot,encode
from device_slot_owners import pack
from audit_snapshot_queries import device


class BoundaryContext(unittest.TestCase):
    def fixture(self):
        recipe,_=recipe_fixture();s,p,_=fixture()
        s['keys'][2]=[0,7,300,-1];s['slots'][2]=[7,300,-1];s['slot_roots'][2]=[7,30,-1]
        s['slot_valid'][2]=[True,True,False]
        for k in ('present','visible','settled'):s[k][2]=True
        b=match(s,p['query'],4,True,True,np)
        return s,b,compile_context(recipe,2,3)

    def test_unselected_neighbor_contributes(self):
        s,b,p=self.fixture();boundary=snapshot(s,np);x,counts=encode(boundary,b,p,np)
        self.assertEqual(counts[0,1].tolist(),[1,0,0])
        changed=deepcopy(boundary);changed['tokens'][2]+=1
        y,_=encode(changed,b,p,np)
        self.assertGreater(np.linalg.norm(x-y),.1)
        np.testing.assert_array_equal(x[~b['live']],0)

    def test_id_renaming_and_owner_layout_do_not_change_features(self):
        s,b,p=self.fixture();x,_=encode(snapshot(s,np),b,p,np)
        renamed=deepcopy(s);bb=deepcopy(b)
        renamed['slot_roots']+=500;bb['slot_roots']+=500
        y,_=encode(snapshot(renamed,np),bb,p,np)
        np.testing.assert_array_equal(x,y)
        packed=pack(s);z,_=encode(snapshot(packed,np),b,p,np)
        np.testing.assert_array_equal(x,z)
        packed['slot_owner']=np.array([2,1,0],np.int32)
        for k in ('slots','slot_roots','slot_valid'):
            packed['owner_'+k]=packed['owner_'+k][[2,1,0]]
        zz,_=encode(snapshot(packed,np),b,p,np)
        np.testing.assert_array_equal(x,zz)

    def test_hidden_stale_or_dirty_sources_never_contribute(self):
        s,b,p=self.fixture()
        for key in ('visible','settled','token_dirty'):
            c=deepcopy(s);c[key][2]=(key=='token_dirty');c['tokens'][2]=np.nan
            x,counts=encode(snapshot(c,np),b,p,np)
            self.assertTrue(np.isfinite(x).all());self.assertEqual(counts[0,1].sum(),0)
        c=pack(s);c['owner_generation'][2]+=1
        _,counts=encode(snapshot(c,np),b,p,np)
        self.assertEqual(counts[0,1].sum(),0)

    def test_typed_connectivity_and_signature_ignore_numeric_identity(self):
        from audit_boundary_context import signature
        s,b,p=self.fixture();recipe,_=recipe_fixture()
        c=dict(rule=np.array(2),bindings=b,boundary=snapshot(s,np))
        key=signature(c,0,recipe,{})
        other=deepcopy(c);other['boundary']['slot_roots']+=500;other['bindings']['slot_roots']+=500
        self.assertEqual(key,signature(other,0,recipe,{}))
        other['target_eq_classes']=np.zeros((1,3),np.int32)
        self.assertEqual(key,signature(other,0,recipe,{}))
        p['port_sorts'][:]=99
        x,counts=encode(c['boundary'],b,p,np)
        np.testing.assert_array_equal(x,0);np.testing.assert_array_equal(counts,0)

    def test_compiled_gpu_matches_reference(self):
        s,b,p=self.fixture();ds,db,dp=map(device,(pack(s),b,p))
        actual=mx.compile(lambda state:encode(snapshot(state,mx),db,dp,mx))(ds)
        mx.eval(actual)
        expected=encode(snapshot(s,np),b,p,np)
        for a,e in zip(actual,expected):np.testing.assert_allclose(np.array(a),e,atol=2e-6)

if __name__=='__main__':unittest.main()
