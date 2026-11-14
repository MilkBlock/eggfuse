import unittest
import numpy as np
import mlx.core as mx
import mlx.nn as nn
from mlx.utils import tree_flatten
from neural_ordered_relations import ordered_model


class Residual(unittest.TestCase):
    def fixture(self):
        base=ordered_model(128,8,True);new=ordered_model(128,8,True,edge_residual=True)
        new.load_weights(list(tree_flatten(base.parameters())),strict=False)
        args=[mx.zeros((2,2,128)),mx.zeros((2,2,2,64)),mx.ones((2,2),mx.bool_),mx.zeros((2,64)),mx.zeros((2,8))]
        args[1]=args[1].at[1,0,0,0].add(1.)
        return base,new,args

    def test_zero_residual_preserves_parent_and_matching(self):
        base,new,args=self.fixture();a,t=base.transition(*args);b,u=new.transition(*args)
        np.testing.assert_array_equal(a,b);np.testing.assert_array_equal(t,u)
        new.edge_residual.weight=new.edge_residual.weight.at[0,0].add(1.)
        b,u=new.transition(*args)
        np.testing.assert_array_equal(a,b);self.assertAlmostEqual(float((u-t)[1,0]),1.,places=6)

    def test_mask_and_gradient(self):
        base,new,args=self.fixture();new.freeze();new.edge_residual.unfreeze()
        _,g=nn.value_and_grad(new,lambda m:mx.sum(m.transition(*args)[1]))(new)
        self.assertTrue(np.any(np.array(g['edge_residual']['weight'])!=0))
        self.assertEqual({k for k,v in tree_flatten(g)},{'edge_residual.weight'})
        new.edge_residual.weight=mx.ones_like(new.edge_residual.weight)
        args[2]=mx.array([[False,True],[False,True]])
        np.testing.assert_allclose(base.transition(*args)[1],new.transition(*args)[1],atol=1e-6)

    def test_invalid_compiled_layout_rejected(self):
        with self.assertRaises(ValueError):ordered_model(127,8,True,edge_residual=True)
        with self.assertRaises(ValueError):ordered_model(128,7,True,edge_residual=True)
        with self.assertRaises(ValueError):ordered_model(128,8,False,edge_residual=True)


if __name__=='__main__':unittest.main()
