import unittest
from collect import dominance, implications


class Implications(unittest.TestCase):
    def setUp(self):
        self.specs = [
            {'table':1,'cols':[0],'guards':[]},
            {'table':2,'cols':[0],'guards':[]},
            {'table':1,'cols':[0],'guards':[[1,[1]]]},
            {'table':1,'cols':[1],'guards':[[1,[1]]]},
        ]
        self.classes = [
            {'driver':0,'guards':[[0,[0]]]},
            {'driver':0,'guards':[[2,[0]]]},
            {'driver':0,'guards':[[3,[0]]]},
            {'driver':0,'guards':[[2,[1]]]},
            {'driver':9,'guards':[[2,[0]]]},
        ]

    def test_stronger_tree_entails_weaker_not_conversely(self):
        proof = implications(self.specs,self.classes)
        self.assertTrue(proof(1,0))
        self.assertFalse(proof(0,1))
        for other in (2,3,4):
            self.assertFalse(proof(other,0), 'projection, receiving port and table identities matter')

    def test_prior_empty_result_is_scoped_to_run_node_and_watermark(self):
        audit = {'specs':self.specs,'classes':self.classes,'dropped_events':0,'events':[
            [1,0,0,0,3,3,3], [1,0,0,1,3,3,3],
            [1,0,1,1,3,3,3], [1,1,0,1,3,3,3], [2,0,0,1,3,3,3]]}
        counts = dominance(audit)['counts']
        self.assertEqual(counts['potential_batches'],1)
        self.assertEqual(counts['implied_probes'],3)
        audit['events'][0][-1] = 2
        self.assertEqual(dominance(audit)['counts'].get('potential_batches',0),0)

    def test_dropped_or_cyclic_evidence_does_not_pass(self):
        with self.assertRaises(AssertionError):
            dominance({'dropped_events':1})
        self.specs[0]['guards'] = [[2,[0]]]
        with self.assertRaises(AssertionError):
            implications(self.specs,self.classes)


if __name__ == '__main__':
    unittest.main()
