import unittest
import numpy as np
import mlx.core as mx
from train_current_cell import CurrentCellModel


class TemplateMatcher(unittest.TestCase):
    def test_matching_preserved_without_dense_state(self):
        mx.random.seed(71)
        model=CurrentCellModel(256,32,3)
        args=(mx.random.normal((5,2,128)),mx.random.normal((5,2,2,64)),
              mx.ones((5,2),mx.bool_),mx.random.normal((5,64)),mx.random.normal((5,32)))
        before,_=model.transition(*args)
        model.template_only=True
        after,tokens=model.transition(*args)
        np.testing.assert_array_equal(before,after)
        np.testing.assert_array_equal(tokens,0.)
        poisoned=tuple(mx.full_like(x,float('nan')) if i in (0,1,3) else x for i,x in enumerate(args))
        logits,_=model.transition(*poisoned)
        np.testing.assert_array_equal(before,logits)


if __name__=='__main__':unittest.main()
