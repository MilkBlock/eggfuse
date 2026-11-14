import unittest
import numpy as np
import mlx.core as mx
from cell_context_features import port_context


class ContextFeatures(unittest.TestCase):
    def test_shared_current_context_and_renaming(self):
        rng=np.random.default_rng(29)
        bank=dict(roots=np.array([[1,2],[1,3],[1,4]]),roles=rng.normal(size=(3,2,64)).astype(np.float32),
                  mask=np.array([True,True,False]),slot_valid=np.ones((3,2),bool))
        query=np.array([[1,2,-1]])
        a=port_context(bank,query)
        b=port_context(dict(bank,roots=bank['roots']+1000),np.where(query>=0,query+1000,-1))
        np.testing.assert_array_equal(a,b)
        np.testing.assert_allclose(a,np.array(port_context(bank,query,mx)),atol=2e-7)
        np.testing.assert_array_equal(a[0,2],0.)
        changed=dict(bank,roles=bank['roles'].copy());changed['roles'][2]*=100
        np.testing.assert_array_equal(a,port_context(changed,query))
        changed['roles'][1,0]*=2
        self.assertFalse(np.allclose(a,port_context(changed,query)))


if __name__=='__main__':unittest.main()
