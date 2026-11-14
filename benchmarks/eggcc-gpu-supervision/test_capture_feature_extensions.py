import unittest
from unittest.mock import patch
import numpy as np
from fit_completion_classifier import assemble_classifier_features
from device_joint_features import compile_projection,expand

class CapturedExtensions(unittest.TestCase):
    def test_recompute_and_do_not_double_append(self):
        base=np.arange(16,dtype=np.float32).reshape(2,8)/16
        extra=np.ones((2,4),np.float32)*.25
        full=expand(np.concatenate([base,extra],axis=1),compile_projection(12),np)
        model=dict(w=np.zeros((2,3),np.float32),coef=np.zeros((8,1),np.float32),boundary_context=True)
        meta=dict(completion_readout=dict(shared_boundary_context=True,joint_features=True))
        data=dict(features=full,boundary_features=base[:,-2:])
        with patch('condition_boundary.captured_bridges',return_value=(extra,0.)):
            x,_=assemble_classifier_features(None,meta,data,model,True,True)
            np.testing.assert_array_equal(x,full);np.testing.assert_array_equal(data['features'],base)
            bad=dict(features=full.copy(),boundary_features=base[:,-2:]);bad['features'][0,-1]+=.1
            with self.assertRaises(ValueError):assemble_classifier_features(None,meta,bad,model,True,True)
            with self.assertRaises(ValueError):assemble_classifier_features(None,{},dict(features=full,boundary_features=base[:,-2:]),model)

if __name__=='__main__':unittest.main()
