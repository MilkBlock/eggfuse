import unittest
import numpy as np
from fit_completion_classifier import ambiguous_rows

class AmbiguousCompletion(unittest.TestCase):
    def test_only_constraint_determined_rows_are_excluded(self):
        states=np.array([[0,0],[1,0],[1,1]],np.float32)
        required=np.array([[0,0],[1,0],[0,1],[1,1]],bool)
        np.testing.assert_array_equal(ambiguous_rows(required,states),[True,True,False,False])
        with self.assertRaises(ValueError):ambiguous_rows(np.array([[0,1]],bool),states[:2])

if __name__=='__main__':unittest.main()
