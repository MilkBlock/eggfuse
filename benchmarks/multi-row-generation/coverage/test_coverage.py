import unittest,sys
from pathlib import Path
import numpy as np
import mlx.core as mx
import mlx.nn as nn
from fixtures import fresh
from objective import penalties,objective
from data import generate,shape,coordinates,N,Q,K,V
from model import SetGenerator,loss


class Coverage(unittest.TestCase):
    def test_fresh_shapes(self):
        old=generate(4096,51900);prior=generate(256,51918,True)
        known={shape(a,b) for d in (old,prior) for a,b in zip(d['a'],d['b'])}
        for family,seed in [('double_triple',61918),('four_left',61919)]:
            d=fresh(256,seed,family)
            self.assertFalse(known&{shape(a,b) for a,b in zip(d['a'],d['b'])})
            self.assertLessEqual(d['targets'][...,0].sum(1).max(),Q)
    def test_soft_coverage_does_not_prove_hard_coverage(self):
        target=np.zeros((1,Q,6),np.int32);target[0,0]=[1,0,0,0,0,0]
        # Two half-active claims sum to one correct soft claim, yet argmax chooses
        # null for both tied logits. Thus the auxiliary loss is not a verifier.
        active=np.tile([30.,-30.],(1,Q,1));active[:,:2]=0
        pointer=np.full((1,Q,2,N),-30.,np.float32);pointer[:,:,:,0]=30
        out=dict(active_logits=mx.array(active),pointer_logits=mx.array(pointer))
        c,n=penalties(out,mx.array(target));mx.eval(c,n)
        self.assertLess(float(c),1e-10);self.assertLess(float(n),1e-10)
        self.assertEqual(int(mx.argmax(out['active_logits'],-1).sum()),0)
    def test_zero_weight_is_original_loss_and_gradient(self):
        mx.random.seed(31);m=SetGenerator();d=generate(4,21);sp,op=map(mx.array,coordinates(4,2));args=(m,mx.array(d['x']),sp,op,mx.array(d['targets']))
        a,ga=nn.value_and_grad(m,loss)(*args);b,gb=nn.value_and_grad(m,objective)(*args,0.0);mx.eval(a,b,ga,gb)
        np.testing.assert_allclose(np.array(a),np.array(b),rtol=1e-6)
        from mlx.utils import tree_flatten
        for (ka,va),(kb,vb) in zip(tree_flatten(ga),tree_flatten(gb)):
            self.assertEqual(ka,kb);np.testing.assert_allclose(np.array(va),np.array(vb),rtol=1e-5,atol=1e-6)

if __name__=='__main__':
    mx.set_default_device(mx.gpu);unittest.main()
