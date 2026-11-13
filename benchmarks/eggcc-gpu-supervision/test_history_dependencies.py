import unittest
from audit_history_dependencies import depths

class HistoryDependencies(unittest.TestCase):
    def test_depth_counts_dependencies_not_duplicate_edges(self):
        order=[(1,0),(2,0),(3,0)]
        self.assertEqual(depths(order,{(2,0):[(1,0)]*3,(3,0):[(2,0)]})[(3,0)],2)
        self.assertEqual(depths(order,{(3,0):[(2,0)]})[(3,0)],1)
        with self.assertRaisesRegex(ValueError,'noncausal'):depths(order,{(1,0):[(3,0)]})

if __name__=='__main__':unittest.main()
