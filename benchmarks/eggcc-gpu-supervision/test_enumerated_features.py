import unittest
import numpy as np
from audit_enumerated_features import diagnose,feature_key

class FeatureAudit(unittest.TestCase):
    def row(self,target,required=False):
        return dict(x=np.array([1.,0.],np.float32),required=np.array([required]),target=target,case=str(target),sample=0,generated=False)

    def test_cross_case_conflict_and_required_constraint(self):
        a,b=self.row(0),self.row(1)
        r=diagnose([a,b],[a])
        self.assertEqual(r['conflicting_input_groups'],1)
        self.assertEqual(r['conflicting_rows'],2)
        self.assertEqual(r['validation'][0]['exact_input_matches'],2)
        self.assertEqual(diagnose([a,self.row(1,True)],[])['conflicting_input_groups'],0)

    def test_classifier_feature_conflicts_cross_sources(self):
        from fit_completion_classifier import feature_conflicts
        x=np.array([[0.,1.],[-0.,1.],[2.,1.]],np.float32)
        y=np.array([[1.,0.],[0.,1.],[0.,1.]],np.float32)
        self.assertEqual(feature_conflicts(x,y)['conflicting_groups'],1)
        extended=np.concatenate([x,np.arange(3)[:,None]],axis=1)
        self.assertEqual(feature_conflicts(extended,y)['conflicting_groups'],0)

    def test_unseen_target_and_wrong_prediction_remain_separate(self):
        train=[self.row(0)]
        known=dict(self.row(0),prediction=1)
        unknown=dict(self.row(1),prediction=1)
        rows=diagnose(train,[known,unknown])['validation']
        self.assertTrue(rows[0]['target_seen'])
        self.assertFalse(rows[0]['correct'])
        self.assertFalse(rows[1]['target_seen'])
        self.assertTrue(rows[1]['correct'])
        self.assertTrue(rows[0]['nearest_correct'])
        self.assertFalse(rows[1]['nearest_correct'])

    def test_signed_zero_and_nonfinite(self):
        self.assertEqual(feature_key([0.],[False]),feature_key([-0.],[False]))
        with self.assertRaises(ValueError):feature_key([np.nan],[False])

if __name__=='__main__':unittest.main()
