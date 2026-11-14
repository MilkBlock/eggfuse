import unittest
import numpy as np
import mlx.core as mx
import test_live_completion_classifier as fixtures
from device_joint_features import compile_projection
from device_join_transition import proposals
from device_completion_classifier import compile_classifier,score_head
from device_match_capture import floating_inputs
from audit_snapshot_queries import device

class LiveJoint(unittest.TestCase):
    def test_compiled_inference_and_independent_capture_replay(self):
        s,p,m,r,h=fixtures.LiveClassifier().fixture()
        w=compile_projection(len(h['mean']));p['joint_projection']=w
        h=dict(h,mean=np.pad(h['mean'],(0,256)),scale=np.pad(h['scale'],(0,256),constant_values=1),coef=np.pad(h['coef'],((0,256),(0,0))))
        h['coef'][-256:]=np.random.default_rng(3).normal(0,.01,h['coef'][-256:].shape)
        p['completion_classifier']=compile_classifier(r,h)
        out,marks=proposals(s,p,dict(w=m['w']),4,True,True,np,True)
        features=floating_inputs(marks['capture'],m,np)
        np.testing.assert_allclose(score_head(features,h,np),marks['capture']['completion_readout']['scores'],atol=2e-6)
        gpu,gm=mx.compile(lambda state:proposals(state,device(p),device(dict(w=m['w'])),4,mx.array(True),mx.array(True),mx,True))(device(s));mx.eval(gpu,gm)
        np.testing.assert_allclose(gpu['tokens'],out['tokens'],atol=2e-6)

if __name__=='__main__':unittest.main()
