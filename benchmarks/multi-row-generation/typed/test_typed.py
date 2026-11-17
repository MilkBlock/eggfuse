import sys,unittest
from pathlib import Path
import numpy as np
import mlx.core as mx
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from task import KEYS,VALUES
from typed_model import tokenize,DIM,WIDTH
from data import fresh,signature,successor

class TypedTests(unittest.TestCase):
    def test_encoding_is_own_prediction_not_repaired_answer(self):
        logits=mx.array(np.random.default_rng(3).normal(size=(5,WIDTH)).astype(np.float32))
        first=tokenize(logits);second=tokenize(logits*3+7);mx.eval(first,second)
        np.testing.assert_array_equal(first,second)
        v=np.array(first);self.assertTrue(np.isin(v,[0.,1.]).all());self.assertTrue((v[:,WIDTH:]==0).all())
        at=0
        for w in (KEYS,KEYS,VALUES,VALUES):
            np.testing.assert_array_equal(v[:,at:at+w].argmax(-1),np.array(logits)[:,at:at+w].argmax(-1));at+=w
        grad=mx.grad(lambda x:mx.sum(tokenize(x)*mx.arange(DIM)))(logits);mx.eval(grad)
        self.assertGreater(float(mx.max(mx.abs(grad))),0)

    def test_signature_ignores_identity_and_distinguishes_tail_shapes(self):
        a=fresh(8,2,8,41817,'two_tails');b=fresh(3,4,8,41818,'two_cycle_tail')
        sa={signature(successor(x,y)) for x,y in zip(a['a'],a['b'])};sb={signature(successor(x,y)) for x,y in zip(b['a'],b['b'])}
        self.assertEqual(len(sa),1);self.assertEqual(len(sb),1);self.assertFalse(sa&sb)
        s=successor(a['a'][0],a['b'][0]);perm=np.random.default_rng(8).permutation(len(s));inv=np.argsort(perm)
        transformed=[int(inv[s[int(perm[i])]]) for i in range(len(s))]
        self.assertEqual(signature(s),signature(transformed))

if __name__=='__main__':unittest.main()
