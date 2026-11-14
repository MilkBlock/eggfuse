import unittest
import numpy as np
import mlx.core as mx
from fit_completion_classifier import fit_normalized_joint_head
from device_completion_classifier import score_head,classifier_features
from audit_snapshot_queries import device

class NormalizedJoint(unittest.TestCase):
    def test_folded_projection_and_gpu_parity(self):
        rng=np.random.default_rng(6)
        x=rng.normal(size=(30,7)).astype(np.float32)
        x[:,0]=1;x[:,1]*=.03
        y=np.eye(2,dtype=np.float32)[np.arange(30)%2]
        h=fit_normalized_joint_head(x,y)
        np.testing.assert_array_equal(h["feature_projection"][0],0)
        changed=x.copy();changed[:,0]=2
        np.testing.assert_array_equal(classifier_features(changed,h,np)[:,:7],changed)
        np.testing.assert_allclose(classifier_features(changed,h,np)[:,7:],classifier_features(x,h,np)[:,7:],atol=2e-6)
        from device_joint_features import compile_projection
        expected=np.tanh(((x-x.mean(0))/np.maximum(x.std(0),.02))@compile_projection(7))
        np.testing.assert_allclose(classifier_features(x,h,np)[:,7:],expected,atol=2e-6)
        actual=mx.compile(lambda z:score_head(z,device(h),mx))(mx.array(x));mx.eval(actual)
        np.testing.assert_allclose(actual,score_head(x,h,np),atol=5e-6)
        with self.assertRaises(ValueError):score_head(x[:,:-1],h,np)

    def test_configurable_width_gpu_parity(self):
        rng=np.random.default_rng(9);x=rng.normal(size=(16,7)).astype(np.float32)
        y=np.eye(2,dtype=np.float32)[np.arange(16)%2]
        h=fit_normalized_joint_head(x,y,hidden=1024)
        self.assertEqual(h["feature_projection"].shape,(7,1024))
        self.assertEqual(h["coef"].shape,(1031,2))
        result=score_head(mx.array(x),device(h),mx);mx.eval(result)
        np.testing.assert_allclose(result,score_head(x,h,np),atol=5e-6)
        with self.assertRaises(ValueError):fit_normalized_joint_head(x,y,hidden=0)

    def test_live_raw_features_flow_directly_into_head(self):
        import test_live_completion_classifier as fixtures
        from device_completion_classifier import compile_classifier,load_head,input_width
        from device_join_transition import proposals
        from device_match_capture import floating_inputs
        state,plan,model,rule,old=fixtures.LiveClassifier().fixture()
        width=old['coef'].shape[0];count=old['coef'].shape[1]
        rng=np.random.default_rng(14)
        train=rng.normal(size=(20,width)).astype(np.float32)
        h=fit_normalized_joint_head(train,np.eye(count,dtype=np.float32)[np.arange(20)%count])
        self.assertEqual(input_width(h),width)
        self.assertEqual(set(load_head({f'head_0_{k}':v for k,v in h.items()},0)),set(h))
        plan['completion_classifier']=compile_classifier(rule,h)
        out,marks=proposals(state,plan,model,4,True,True,np,True)
        raw=floating_inputs(marks['capture'],model,np)
        self.assertEqual(raw.shape[1],width)
        self.assertNotIn('joint_features',marks['capture']['request'])
        np.testing.assert_allclose(score_head(raw,h,np),marks['capture']['completion_readout']['scores'],atol=5e-6)
        gpu,gm=mx.compile(lambda v:proposals(v,device(plan),device(model),4,mx.array(True),mx.array(True),mx,True))(device(state));mx.eval(gpu,gm)
        np.testing.assert_allclose(gpu['tokens'],out['tokens'],atol=5e-6)
        bad=dict(h);del bad['feature_center']
        with self.assertRaises(ValueError):compile_classifier(rule,bad)
        with self.assertRaises(ValueError):compile_classifier(rule,dict(h,feature_center=h['feature_center'][:-1]))

if __name__=='__main__':unittest.main()
