import unittest
import numpy as np
import mlx.core as mx
from device_source_relations import encode

class Relations(unittest.TestCase):
    def test_grouping_not_numeric_identity_and_masked_padding(self):
        c=np.random.default_rng(2).normal(size=(1,4,128)).astype(np.float32)
        valid=np.array([[1,1,1,0]],bool)
        first=encode(np.array([[7,7,8,-1]]),c,valid,np)
        np.testing.assert_array_equal(first,encode(np.array([[99,99,15,99]]),c,valid,np))
        changed=encode(np.array([[7,8,7,-1]]),c,valid,np)
        self.assertGreater(np.max(abs(first-changed)),.01)
        np.testing.assert_array_equal(encode(np.array([[1,2,3,4]]),c,valid,np),np.zeros((1,128)))
        np.testing.assert_allclose(first,np.tanh(c[:,0]*c[:,1]),atol=1e-6)

    def test_compiled_gpu_and_permuted_edges(self):
        c=np.random.default_rng(3).normal(size=(2,5,128)).astype(np.float32)
        src=np.array([[1,1,2,1,2],[4,5,6,7,8]],np.int32);v=np.ones_like(src,bool)
        expected=encode(src,c,v,np)
        perm=[4,1,3,2,0]
        np.testing.assert_allclose(expected,encode(src[:,perm],c[:,perm],v[:,perm],np),atol=2e-6)
        out=mx.compile(lambda s,c,v:encode(s,c,v,mx))(mx.array(src),mx.array(c),mx.array(v));mx.eval(out)
        np.testing.assert_allclose(expected,np.array(out),atol=2e-6)

    def test_real_entry_path_consumes_relations_without_host_feature_readback(self):
        from test_device_entry_transition import EntryTransition
        from test_lower_device_entries import recipe
        from cell_token_successors import compile_catalog
        from lower_device_entries import lower
        from device_entry_transition import compile_features,step
        state,plan,_,_,_=EntryTransition().fixture()
        r=recipe(True);entry=lower(r,compile_catalog(r),source_slots=True)['entries'][0]
        layout,coeff=compile_features(r,entry,source_relations=True)
        rng=np.random.default_rng(88)
        model=dict(w=rng.normal(0,.01,(1536,16)).astype(np.float32),coef=rng.normal(0,.01,(1553,128)).astype(np.float32))
        expected,marks=step(state,plan,layout,coeff,model,np.array(0),np)
        dev=lambda d:{k:mx.array(v) for k,v in d.items()}
        p,l,c,m=map(dev,(plan,layout,coeff,model))
        out,dm=mx.compile(lambda s:step(s,p,l,c,m,mx.array(0),mx))(dev(state));mx.eval(out,dm)
        self.assertTrue(marks['admission']['accepted'].any())
        np.testing.assert_allclose(np.array(out['tokens']),expected['tokens'],atol=3e-6)

    def test_multi_source_match_selects_compiled_relation_coefficients(self):
        from test_device_join_transition import fixture,device_plan
        from test_device_query_join import fixture as query_fixture
        from device_join_transition import compile_transition,step
        state,_,_=fixture();recipe,_=query_fixture()
        plan=compile_transition(recipe,2,source_relations=True)
        rng=np.random.default_rng(89)
        model=dict(w=rng.normal(0,.01,(1536,16)).astype(np.float32),coef=rng.normal(0,.01,(1553,128)).astype(np.float32))
        expected,marks=step(state,plan,model,4,True,True,np)
        p=device_plan(plan);m={k:mx.array(v) for k,v in model.items()}
        out,dm=mx.compile(lambda s:step(s,p,m,4,mx.array(True),mx.array(True),mx))({k:mx.array(v) for k,v in state.items()});mx.eval(out,dm)
        self.assertTrue(marks['admission']['accepted'].any())
        np.testing.assert_allclose(np.array(out['tokens']),expected['tokens'],atol=3e-6)
        self.assertFalse(np.array(dm['admission']['transferred']).any())

if __name__=='__main__':unittest.main()
