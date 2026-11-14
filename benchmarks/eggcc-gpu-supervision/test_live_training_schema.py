import unittest
import numpy as np
from calibrate_semantic_family import align_features


class LiveTrainingSchema(unittest.TestCase):
    def fixture(self):
        data=dict(features=np.ones((2,4),np.float32),boundary_features=np.full((2,2),.3,np.float32))
        model=dict(w=np.zeros((2,1),np.float32),coef=np.ones((4,1),np.float32))
        return data,model

    def test_offline_addition_and_live_retraining_share_same_basis(self):
        data,model=self.fixture();x,coef=align_features(data,model,True)
        self.assertEqual(x.shape,(2,6));np.testing.assert_array_equal(coef[4:],0)
        live=dict(data,features=x);trained=dict(model,coef=coef+.1,boundary_context=True)
        xx,cc=align_features(live,trained,True)
        np.testing.assert_array_equal(xx,x);np.testing.assert_array_equal(cc,trained['coef'])
        self.assertEqual(xx.shape,(2,6))
        np.testing.assert_array_equal(data['features'],1)

    def test_disagreeing_live_columns_or_implicit_truncation_rejected(self):
        data,model=self.fixture();x,coef=align_features(data,model,True)
        trained=dict(model,coef=coef,boundary_context=True)
        with self.assertRaises(ValueError):align_features(dict(data,features=x+.1),trained,True)
        with self.assertRaises(ValueError):align_features(dict(data,features=x),trained,False)
        with self.assertRaises(ValueError):align_features(data,dict(model,boundary_context=True),True)

    def test_plain_base_remains_unchanged(self):
        data,model=self.fixture();x,coef=align_features(data,model,False)
        np.testing.assert_array_equal(x,data['features']);np.testing.assert_array_equal(coef,model['coef'])

if __name__=='__main__':unittest.main()
