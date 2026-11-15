import unittest
import numpy as np
import mlx.core as mx
from device_prefix_match import expand


class PrefixDecode(unittest.TestCase):
    def fixture(self):
        bank=dict(roots=mx.array([[0,1]]),roles=mx.ones((1,2,64)),mask=mx.array([True]),slot_valid=mx.ones((1,2),mx.bool_))
        pool=dict(roots=mx.array([[0],[1]]),entries=mx.array([[0,0],[1,0]]),live=mx.array([True,True]))
        return bank,pool

    def test_all_branches_and_overflow(self):
        bank,pool=self.fixture();model=lambda x:mx.ones((len(x),1))
        full=expand(bank,[pool,pool],mx.zeros(64),model,2,1,4,mx)
        self.assertTrue(bool(full['complete']));self.assertEqual(int(mx.sum(full['live'])),4)
        expected={(0,0),(0,1),(1,0),(1,1)}
        self.assertEqual({tuple(v[:,0]) for v in np.array(full['entries'])},expected)
        small=expand(bank,[pool,pool],mx.zeros(64),model,2,1,2,mx)
        self.assertTrue(bool(small['overflow']));self.assertFalse(bool(small['complete']))

    def test_nonfinite_and_empty_are_distinct(self):
        bank,pool=self.fixture()
        bad=expand(bank,[pool],mx.zeros(64),lambda x:mx.full((len(x),1),float('nan')),1,1,2,mx)
        self.assertFalse(bool(bad['complete']));self.assertTrue(bool(bad['nonfinite']))
        empty=expand(bank,[pool],mx.zeros(64),lambda x:-mx.ones((len(x),1)),1,1,2,mx)
        self.assertFalse(bool(empty['complete']));self.assertTrue(bool(empty['proposal_complete']));self.assertFalse(bool(mx.any(empty['live'])))


if __name__=='__main__':unittest.main()
