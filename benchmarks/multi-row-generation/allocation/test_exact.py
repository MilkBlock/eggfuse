"""Audit exact GPU packing on the complete frozen panels, including empty joins."""
import unittest
from pathlib import Path
import numpy as np
import mlx.core as mx
from data import coordinates,audit
from benchmark_allocation import exact
from model import verify


class ExactComparator(unittest.TestCase):
    def test_complete_panels(self):
        mx.set_default_device(mx.gpu)
        root=Path('/Volumes/EggFuseWorkspace/experiments/multi-row-allocation-20261118/joint-1703')
        for panel in ('iid','multiplicity'):
            with np.load(root/f'{panel}-4x2.npz') as z:a=z['a'];b=z['b']
            for rows,length in ((4,2),(2,4)):
                sp=mx.array(coordinates(rows,length)[0]);aa=mx.array(a);bb=mx.array(b);out=exact(aa,bb,sp);passed=verify(aa,bb,out);mx.eval(out,passed)
                self.assertTrue(np.array(passed).all())
                self.assertEqual(audit(a,b,{k:np.array(v) for k,v in out.items()},np.array(sp))['complete_graphs'],256)

if __name__=='__main__':unittest.main()
