import unittest
import numpy as np
from cell_source_origin import initial_instances,generated

class SourceOrigin(unittest.TestCase):
    def test_identity_includes_generation(self):
        state=dict(present=np.array([True,False,True]),generation=np.array([1,0,7]))
        initial=initial_instances(state)
        self.assertEqual(initial,{'0':1,'2':7})
        np.testing.assert_array_equal(generated([0,0,1,2,2],[1,2,1,7,8],initial),[False,True,True,False,True])
        with self.assertRaises(ValueError):generated([0],[1,2],initial)

if __name__=='__main__':unittest.main()
