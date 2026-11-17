import unittest,itertools
import numpy as np
from assignment import assign
from data import generate,truth,audit,coordinates,shape,Q


class Contracts(unittest.TestCase):
    def test_assignment_against_exhaustive(self):
        rng=np.random.default_rng(7)
        for n in (1,2,4):
            costs=rng.normal(size=(13,n,n));chosen=assign(costs)
            for c,p in zip(costs,chosen):
                self.assertEqual(len(set(p)),n)
                best=min(sum(c[i,j] for i,j in enumerate(order)) for order in itertools.permutations(range(n)))
                self.assertAlmostEqual(c[np.arange(n),p].sum(),best)
        self.assertEqual(len(set(assign(np.zeros((1,4,4)))[0])),4)
    def test_sets_and_shapes(self):
        d=generate(128,13);h=generate(128,17,held=True)
        self.assertFalse({shape(a,b) for a,b in zip(d['a'],d['b'])}&{shape(a,b) for a,b in zip(h['a'],h['b'])})
        sp,_=coordinates(4,2);t=d['targets'];p=t[...,1:3]
        out=dict(active=t[...,0],pointers=p,fields=t[...,3:],addresses=np.stack((sp[p[...,0]],sp[4+p[...,1]]),-2))
        self.assertEqual(audit(d['a'],d['b'],out,sp)['complete_graphs'],128)
        g=next(g for g in range(128) if 1<len(truth(d['a'][g],d['b'][g]))<Q)
        for key in out:out[key]=out[key].copy();out[key][g,1]=out[key][g,0]
        report=audit(d['a'],d['b'],out,sp);self.assertEqual(report['complete_graphs'],127);self.assertGreater(report['duplicates'],0);self.assertGreater(report['missing'],0)
    def test_model_gradient_and_gpu_verifier(self):
        import mlx.core as mx
        import mlx.nn as nn
        from model import SetGenerator,loss,assignment_cost,decode,verify
        mx.set_default_device(mx.gpu);d=generate(8,23);sp,op=map(mx.array,coordinates(4,2));m=SetGenerator();x=mx.array(d['x']);t=mx.array(d['targets'])
        costs=assignment_cost(m(x,sp,op),t);mx.eval(costs);p=assign(np.array(costs));aligned=mx.array(d['targets'][np.arange(8)[:,None],p])
        value,grad=nn.value_and_grad(m,loss)(m,x,sp,op,aligned);mx.eval(value,grad);self.assertTrue(np.isfinite(float(value)))
        target=d['targets'];fake=dict(active=mx.array(target[...,0]),pointers=mx.array(target[...,1:3]),fields=mx.array(target[...,3:]))
        self.assertTrue(np.array(verify(mx.array(d['a']),mx.array(d['b']),fake)).all())
        out=decode(m(x,sp,op),sp);mx.eval(out);cpu={k:np.array(v) for k,v in out.items()};gpu=np.array(verify(mx.array(d['a']),mx.array(d['b']),out));self.assertEqual(int(gpu.sum()),audit(d['a'],d['b'],cpu,np.array(sp))['complete_graphs'])

if __name__=='__main__':unittest.main()
