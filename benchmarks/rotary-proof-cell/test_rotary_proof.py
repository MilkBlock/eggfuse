import unittest
import numpy as np
import mlx.core as mx
from model import address, rebase, rotate, CellNet
from contract import labels, verify, batch

class Contract(unittest.TestCase):
    def test_all_finite_symbolic_cases(self):
        for initial in range(2):
            for same in range(2):
                for slot in range(5):
                    for tag in [0, 85, 165, 255]:
                        case=(initial,same,slot,tag)
                        self.assertEqual(verify(case,labels(case)),[])
    def test_reject_wrong_union_and_pending(self):
        c=(0,1,2,165); h=labels(c); h[0]['eq'][0]=1
        self.assertTrue(verify(c,h))
        c=(0,0,2,165); h=labels(c); h[2]['pending'][1]=0
        self.assertTrue(verify(c,h))
    def test_union_preserves_roles_and_accepts_equivalent_argument(self):
        c=(0,1,2,165); h=labels(c); h[2]['g_arg']=[3]
        self.assertEqual(verify(c,h),[])
        h[2]['alias'][2]=h[2]['alias'][3]
        self.assertTrue(verify(c,h))  # Eq(u,v) does not erase the logical u/v roles.
    def test_initial_equality_does_not_forge_samevalue(self):
        c=(1,0,2,165); h=labels(c)
        self.assertEqual(verify(c,h),[])
        h[1]['proof']=[1]; h[1]['premises']=[1,2,5]
        self.assertTrue(verify(c,h))
    def test_rotary_axes_and_nonuniform_projection(self):
        a=address(mx.array([1]),mx.array([2])); b=address(mx.array([2]),mx.array([1]))
        self.assertFalse(np.allclose(a,b))
        old_c=mx.array([[5]]); new_c=mx.array([[9]]); p=mx.array([[0,1,2,3]]); q=mx.array([[0,1,3,4]])
        projected=rebase(address(old_c,p),old_c,p,new_c,q)
        np.testing.assert_allclose(projected,address(new_c,q),atol=1e-6)
        key=mx.arange(128).astype(mx.float32)[None,:]/128
        np.testing.assert_allclose(rotate(rotate(key,mx.array([4095]),'cell'),mx.array([4095]),'cell',True),key,atol=1e-6)
    def test_runtime_has_no_teacher_argument_and_is_recurrent(self):
        m=CellNet(); seed,_=batch([(0,1,2,165)]); pos=mx.array([[0,5,9]])
        output=m.rollout(mx.array(seed),pos);mx.eval(output)
        gradient=mx.grad(lambda x:mx.sum(m.rollout(x,pos)['logits'][2]**2))(mx.array(seed));mx.eval(gradient)
        self.assertGreater(float(mx.max(mx.abs(gradient))),0.)
        token=rotate(m.encoder(mx.array(seed)),pos[:,0],'cell'); at=pos[:,0]
        for phase in range(3):
            token,at,score,owner=m.advance(token,at,phase,pos)
            np.testing.assert_array_equal(token,output['tokens'][phase])

if __name__=='__main__': unittest.main()
