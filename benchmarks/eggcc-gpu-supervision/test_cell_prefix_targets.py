import unittest
import numpy as np
from cell_prefix_targets import build


class Prefixes(unittest.TestCase):
    def test_distinct_exports_and_dead_prefixes_are_preserved(self):
        data=dict(entry_sources=np.array([[1,2],[1,2],[1,3],[4,3]]),
                  entry_records=np.array([[0,0],[0,1],[1,0],[0,0]]),
                  valid=np.array([1,1,0,0]),case=np.zeros(4,int),rule=np.zeros(4,int))
        rows=build(data);root=next(r for r in rows if not r['prefix'])
        self.assertEqual(root['legal_next'],[(1,0)])
        live=next(r for r in rows if r['prefix']==((1,0),))
        self.assertEqual(live['legal_next'],[(2,0),(2,1)])
        dead=next(r for r in rows if r['prefix']==((1,1),))
        self.assertEqual(dead['legal_next'],[])


if __name__=='__main__':unittest.main()
