import unittest
import numpy as np
from summarize_enumerated_gpu import prediction_counts

class CollectionPrediction(unittest.TestCase):
    def test_direct_generated_and_mismatch(self):
        row=dict(y=np.array([True,False]),quotient=dict(representatives=np.array([0,1])))
        out=prediction_counts([row,row],[np.array([1,0]),np.array([1,1])],[False,True])
        self.assertEqual(out['all'],dict(instances=2,correct=1))
        self.assertEqual(out['direct']['correct'],1);self.assertEqual(out['generated']['correct'],0)
        with self.assertRaises(ValueError):prediction_counts([row],[],[False])
        with self.assertRaises(ValueError):prediction_counts([row],[np.array([1])],[False])

if __name__=='__main__':unittest.main()
