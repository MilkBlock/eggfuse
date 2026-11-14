import unittest
import numpy as np
import mlx.core as mx
import test_live_completion_classifier as fixtures
from device_join_transition import proposals
from device_match_capture import floating_inputs
from audit_snapshot_queries import device

class CaptureReference(unittest.TestCase):
    def test_high_precision_only_changes_projection_accumulation(self):
        state,plan,model,_,_=fixtures.LiveClassifier().fixture()
        _,marks=proposals(state,plan,model,4,True,True,np,True)
        c=marks['capture'];normal=floating_inputs(c,model,np)
        precise=floating_inputs(c,model,np,reference=True)
        n,h=model['w'].shape
        np.testing.assert_array_equal(normal[:,:1+n],precise[:,:1+n])
        expected=np.tanh((normal[:,1:1+n].astype(np.float64)@model['w'].astype(np.float64)).astype(np.float32))
        np.testing.assert_array_equal(precise[:,1+n:1+n+h],expected)
        self.assertEqual(precise.dtype,normal.dtype)
        with self.assertRaises(ValueError):floating_inputs(device(c),device(dict(w=model['w'])),mx,reference=True)

if __name__=='__main__':unittest.main()
