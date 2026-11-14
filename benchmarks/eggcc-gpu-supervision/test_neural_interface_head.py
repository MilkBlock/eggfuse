import unittest
import numpy as np
import mlx.core as mx
from neural_ordered_relations import InterfaceCellTransition


class InterfaceHead(unittest.TestCase):
    def test_matching_invariant_to_token_contents_but_successor_is_not(self):
        mx.random.seed(42);model=InterfaceCellTransition(16,20,32)
        model.match_relation.weight=mx.random.normal(model.match_relation.weight.shape)
        relations=mx.random.normal((4,20));source=mx.random.normal((4,2,128));edge=mx.random.normal((4,2,2,64))
        request=mx.random.normal((4,64));mask=mx.ones((4,2),mx.bool_)
        a=model.transition(source,edge,mask,request,relations)
        b=model.transition(-source*3,edge+4,mask,-request,relations);mx.eval(a,b)
        np.testing.assert_array_equal(a[0],b[0])
        self.assertFalse(np.allclose(a[1],b[1]))
        gradient=mx.grad(lambda x:mx.sum(model.transition(x,edge,mask,request,relations)[1]))(source)
        self.assertTrue(np.any(np.abs(np.array(gradient))>1e-8))

    def test_interface_changes_can_change_the_match(self):
        mx.random.seed(43);model=InterfaceCellTransition(16,20,32)
        model.match_relation.weight=mx.random.normal(model.match_relation.weight.shape)
        source=mx.zeros((2,2,128));edge=mx.zeros((2,2,2,64));mask=mx.ones((2,2),mx.bool_);request=mx.zeros((2,64))
        relations=mx.stack([mx.zeros(20),mx.ones(20)])
        logits,_=model.transition(source,edge,mask,request,relations)
        self.assertNotAlmostEqual(float(logits[0]),float(logits[1]),places=6)


if __name__=='__main__':unittest.main()
