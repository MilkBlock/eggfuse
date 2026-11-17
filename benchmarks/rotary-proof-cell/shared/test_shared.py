import unittest
import numpy as np
import mlx.core as mx
import mlx.nn as nn
from abi import *
from shared_net import SharedNet,parts,unpack,decode_local,rotate,loss
from cpu_contract import cpu_scores
from semantics import decode,targets
from spec import sample,seed_inputs,positions

class SharedTests(unittest.TestCase):
    def test_protected_input_and_real_recurrence(self):
        if not mx.metal.is_available():self.fail('Metal is required')
        mx.set_default_device(mx.gpu)
        rng=np.random.default_rng(40);m=SharedNet();x=mx.array(seed_inputs(sample('joint',4,rng)));p=mx.array(positions(4,rng))
        out=m.rollout(x,p,False);mx.eval(out)
        for s in range(3):np.testing.assert_array_equal(out['tokens'][s,:,PTR_END:SEED_END],x)
        token,at,score,owner=m.advance(out['tokens'][1],out['locations'][1],2,p);mx.eval(token,score)
        np.testing.assert_array_equal(token,out['tokens'][2]);np.testing.assert_array_equal(score,out['logits'][2])
        self.assertEqual(token.shape[-1],279)

    def test_shared_local_pointer_features_translate(self):
        m=SharedNet()
        left=m.pointer_matrix(mx.array([1]));right=m.pointer_matrix(mx.array([4]));mx.eval(left,right)
        np.testing.assert_allclose(np.array(left)[0,1,0:3],np.array(right)[0,4,3:6],atol=1e-6)
        self.assertEqual(m.pointer.layers[0].weight.shape[1],8)
        self.assertEqual(m.relation.layers[0].weight.shape[1],8)

    def test_training_gradient_and_independent_decoder(self):
        rng=np.random.default_rng(11);c=sample('seen',3,rng);m=SharedNet()
        x=mx.array(seed_inputs(c));p=mx.array(positions(3,rng));y={k:mx.array(v) for k,v in targets(c).items()}
        value,gradient=nn.value_and_grad(m,loss)(m,x,p,y);mx.eval(value,gradient)
        self.assertTrue(np.isfinite(float(value)))
        self.assertGreater(float(mx.max(mx.abs(gradient['relation']['layers'][0]['weight']))),0.)
        self.assertGreater(float(mx.max(mx.abs(gradient['pointer']['layers'][0]['weight']))),0.)
        r=m.rollout(x,p,False);mx.eval(r)
        actual=decode(cpu_scores(np.array(r['tokens']),np.array(r['locations'])))
        gpu=decode(np.array(r['logits']))
        for k in SPECS:np.testing.assert_array_equal(actual[k],gpu[k])

if __name__=='__main__':unittest.main()
