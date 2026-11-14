import unittest
import numpy as np
import mlx.core as mx
from device_owner_relations import context
from device_ridge_transition import encode_features,infer
from device_slot_owners import pack,transfer
from test_device_slot_owners import fixture

class OwnerRelations(unittest.TestCase):
    def test_sharing_generation_and_padding(self):
        _,state,_=fixture();s=pack(state)
        source=np.array([[0,1,-99]],np.int32);valid=np.array([[True,True,False]])
        roles=np.array([[[.3,-.7],[.8,.4],[float('nan'),float('nan')]]],np.float32)
        a,missing=context(s,source,valid,roles,np)
        np.testing.assert_array_equal(a,0);self.assertFalse(missing.any())
        s['slot_owner'][0]=1
        b,missing=context(s,source,valid,roles,np)
        self.assertTrue(np.isfinite(b).all());self.assertTrue(np.any(b!=0));self.assertFalse(missing.any())
        s['owner_epoch'][0]+=1
        _,missing=context(s,source,valid,roles,np);self.assertTrue(missing.all())

    def test_compiled_join_admits_with_owner_context(self):
        if not mx.metal.is_available():self.skipTest('Metal required')
        import test_device_join_transition as jf
        from device_join_transition import compile_transition,step
        recipe,_=jf.query_fixture.fixture();s,_,_=jf.fixture();s=pack(s)
        plan=compile_transition(recipe,2,owner_relations=True)
        rng=np.random.default_rng(112)
        model=dict(w=rng.normal(0,.01,(1536,16)).astype(np.float32),coef=rng.normal(0,.01,(1553,128)).astype(np.float32))
        expected,em=step(s,plan,model,4,True,True,np,capture=True)
        dp=jf.device_plan(plan);dm={k:mx.array(v) for k,v in model.items()}
        out,marks=mx.compile(lambda state:step(state,dp,dm,4,mx.array(True),mx.array(True),mx,capture=True))({k:mx.array(v) for k,v in s.items()});mx.eval(out,marks)
        self.assertEqual(int(mx.sum(marks['admission']['accepted'])),1)
        from device_match_capture import floating_inputs,host
        cap=host(marks['capture']);features=floating_inputs(cap,model,np)
        live_features,_=encode_features(s,cap['request'],model,np)
        np.testing.assert_allclose(features,live_features,atol=2e-6)
        self.assertIn('owner_epoch',cap['source_owner_context'])
        from device_match_capture import audit
        self.assertTrue(audit(recipe,cap)['passed'])
        cap['source_owner_context']['owner_epoch'][0,0]+=1
        self.assertFalse(audit(recipe,cap)['passed'])
        del cap['source_owner_context']
        with self.assertRaises(ValueError):floating_inputs(cap,model,np)
        np.testing.assert_allclose(np.array(out['tokens']),expected['tokens'],atol=2e-6)

    def test_gpu_transfer_feeds_next_float_inference(self):
        if not mx.metal.is_available():self.skipTest('Metal required')
        _,state,plan=fixture();s=pack(state);rng=np.random.default_rng(71)
        rand=lambda shape:rng.normal(0,.3,shape).astype(np.float32)
        s.update(tokens=rand((2,4)),token_dirty=np.zeros(2,bool))
        request=dict(sources=np.array([[0,1]],np.int32),generations=np.array([[2,5]],np.int32),edge_valid=np.ones((1,2),bool),input_ready=np.ones(1,bool),seed=rand((1,4)),q=rand((1,3)),edge=rand((1,2,4)),route=rand((1,2,2)),owner_relation=rand((1,2,5)))
        model=dict(w=rand((28,8)),coef=rand((37,4)))
        before,_=encode_features(s,request,model,np)
        out,marks=transfer(s,plan,np.array(0),np.array(1),np.array(2),np.array(5),np.array(True),np)
        self.assertTrue(marks['transferred'])
        after,ready=encode_features(out,request,model,np)
        self.assertTrue(ready['ready'].all());self.assertFalse(np.allclose(before,after))
        expected,_=infer(out,request,model,np)
        dev=lambda d:{k:mx.array(v) if isinstance(v,np.ndarray) else v for k,v in d.items()}
        dp,dr,dm=map(dev,(plan,request,model))
        def step(st):
            moved,transfer_marks=transfer(st,dp,mx.array(0),mx.array(1),mx.array(2),mx.array(5),mx.array(True),mx)
            token,inference_marks=infer(moved,dr,dm,mx)
            return token,inference_marks,transfer_marks
        token,im,tm=mx.compile(step)(dev(s));mx.eval(token,im,tm)
        self.assertTrue(bool(tm['transferred']));self.assertTrue(bool(im['ready'][0]))
        np.testing.assert_allclose(np.array(token),expected,atol=2e-6)
        out['owner_epoch'][0]+=1
        self.assertFalse(infer(out,request,model,np)[1]['ready'][0])

if __name__=='__main__':unittest.main()
