import unittest
from pathlib import Path
import numpy as np
import mlx.core as mx
import mlx.nn as nn
from stream_model import StreamGenerator
from stream_objective import objective
from stream_data import fresh
from stream_metrics import check_token
from data import generate,coordinates,shape
from model import decode


class Streaming(unittest.TestCase):
    def test_history_is_generated_and_causal(self):
        mx.random.seed(41);m=StreamGenerator('feedback');blind=StreamGenerator('blind');blind.update(m.parameters())
        d=generate(4,43);x=mx.array(d['x'])
        for rows,length in ((4,2),(2,4)):
            sp,op=map(mx.array,coordinates(rows,length));full=m(x,sp,op,rows,length);erased=m(x,sp,op,rows,length,'erase');other=blind(x,sp,op,rows,length);mx.eval(full,erased,other)
            first=np.arange(0,8,length);later=np.setdiff1d(np.arange(8),first)
            for k in full:
                np.testing.assert_array_equal(np.array(full[k])[:,first],np.array(erased[k])[:,first]);np.testing.assert_array_equal(np.array(erased[k]),np.array(other[k]))
            self.assertGreater(float(mx.max(mx.abs(full['latent'][:,mx.array(later)]-erased['latent'][:,mx.array(later)]))),1e-4)
            decoded=decode(full,sp);mx.eval(decoded);check_token({**{k:np.array(v) for k,v in full.items()},**{k:np.array(v) for k,v in decoded.items()}},np.array(sp))
    def test_gradient_through_history(self):
        mx.random.seed(47);m=StreamGenerator();d=generate(4,49);sp,op=map(mx.array,coordinates(4,2))
        value,g=nn.value_and_grad(m,objective)(m,mx.array(d['x']),sp,op,4,2,mx.array(d['targets']));mx.eval(value,g)
        self.assertTrue(np.isfinite(float(value)));self.assertGreater(float(mx.sum(mx.abs(g['history_encoder']['weight']))),0)
    def test_fresh_directed_shapes(self):
        known=set();d=generate(4096,51900);known.update(shape(a,b) for a,b in zip(d['a'],d['b']))
        root=Path('/Volumes/EggFuseWorkspace/experiments')
        for experiment,model in [('multi-row-allocation-20261118','joint-1703'),('multi-row-coverage-20261118','control-joint-1703')]:
            for path in (root/experiment/model).glob('*.npz'):
                with np.load(path) as z:known.update(shape(a,b) for a,b in zip(z['a'],z['b']))
        for family,seed in [('triple_right',71918),('four_right',71919)]:
            d=fresh(256,seed,family);self.assertFalse(known&{shape(a,b) for a,b in zip(d['a'],d['b'])})

if __name__=='__main__':
    mx.set_default_device(mx.gpu);unittest.main()
