import unittest
import numpy as np
import mlx.core as mx
from network import StructureNet
from spec import seed_inputs,sample,positions

class GeneratedLatent(unittest.TestCase):
    def test_actual_recurrence_and_input_dependence(self):
        if not mx.metal.is_available():self.fail('Metal required')
        mx.set_default_device(mx.gpu)
        rng=np.random.default_rng(4);m=StructureNet()
        x=mx.array(seed_inputs(sample('joint',4,rng)));p=mx.array(positions(4,rng))
        r=m.rollout(x,p,read=False)
        token,where,score,owner=m.advance(r['tokens'][1],r['locations'][1],2,p)
        mx.eval(r,token,where,score,owner)
        np.testing.assert_array_equal(token,r['tokens'][2])
        np.testing.assert_array_equal(score,r['logits'][2])
        gradient=mx.grad(lambda v:mx.sum(m.rollout(v,p,read=False)['logits'][2]**2))(x)
        mx.eval(gradient);self.assertGreater(float(mx.max(mx.abs(gradient))),0.)

if __name__=='__main__':unittest.main()
