import unittest
import numpy as np
from audit_token_information import ambiguity

class TokenInformation(unittest.TestCase):
    def test_conflicts_count_minimum_query_errors_without_crossing_scopes(self):
        x=np.array([[1,2]]*4+[[2,3]],np.float32);y=np.array([False,False,True,True,True])
        report=ambiguity(x,y,['a','a','a','b','a'],list(range(5)))
        self.assertEqual(report['conflicting_features'],1)
        self.assertEqual(report['queries_in_conflicts'],3)
        self.assertEqual(report['unavoidable_query_errors'],1)
        self.assertEqual(report['witnesses'][0]['negative'],0)
        self.assertEqual(report['witnesses'][0]['positive'],2)

    def test_actual_f32_rounding_and_signed_zero(self):
        x=np.array([[1.,0.],[1.+1e-10,-0.]],np.float64)
        self.assertEqual(ambiguity(x,[False,True],['a','a'],[0,1])['conflicting_features'],1)
        with self.assertRaisesRegex(ValueError,'nonfinite'):ambiguity([[float('nan')]],[False],['a'],[0])
        self.assertEqual(ambiguity(np.zeros((0,3)),[],[],[])['queries'],0)

if __name__=='__main__':unittest.main()
