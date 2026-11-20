from itertools import combinations,product
import unittest
import numpy as np
from fit import Trace

class BudgetOracleTest(unittest.TestCase):
    def test_prices_match_exhaustive_choices_including_exit_and_idle(self):
        trace=Trace.__new__(Trace)
        trace.samples=np.zeros((4,3,8),dtype=np.int64)
        trace.samples[:,:,0]=[[0,0,0],[2,4,1],[3,0,2],[1,4,5]]
        trace.samples[:,:,6]=[[3,0,0],[4,2,1],[1,0,9],[1,7,3]]
        trace.live=trace.samples[:,:,0]
        trace.unions=np.array([1,0,2,0])
        trace.gain=trace.samples[:,:,6]-trace.unions[:,None]
        for budget in (1,2):
            choices=[[set(c) for size in range(budget+1) for c in combinations(np.flatnonzero(row),size)]
                     for row in trace.live]
            optimum=max(trace.work(path)['priced_work'] for path in product(*choices))
            self.assertEqual(trace.work(trace.oracle(budget))['priced_work'],optimum)
