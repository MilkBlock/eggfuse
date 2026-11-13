import unittest
import numpy as np
from multi_entry_ridge import context_route

class ContextRoute(unittest.TestCase):
    def test_split_preserves_roles_and_separates_origin(self):
        r=np.array([1,.2,-.5,.7],np.float32)
        a=context_route(r,False,'class-history-split');b=context_route(r,True,'class-history-split')
        np.testing.assert_array_equal(a[:4],r);np.testing.assert_array_equal(b[4:],r)
        self.assertEqual(float(a@b),0)
        c=context_route(r,False,'class-history-repeat');d=context_route(r,True,'class-history-repeat')
        np.testing.assert_array_equal(c,d)
        np.testing.assert_allclose(c@c,r@r,rtol=1e-6)

if __name__=='__main__':unittest.main()
