import unittest
import numpy as np
from audit_training_expansion import summarize

class TrainingExpansion(unittest.TestCase):
    def test_full_pairs_are_audited_after_shared_class_score(self):
        rows=[dict(pairs=[(0,1),(0,2),(1,2)],y=np.array([True,False,False]),
            quotient=dict(representatives=np.array([1]),expansion=np.array([-1,0,0])))]
        wrong=summarize(rows,np.array([.9]));right=summarize(rows,np.array([.1]))
        self.assertEqual(wrong['false_merges'],2)
        self.assertEqual(right['exact_partitions'],1)
        self.assertEqual(wrong['query_instances'],right['query_instances'])
        with self.assertRaisesRegex(ValueError,'alignment'):summarize(rows,np.array([.1,.2]))

if __name__=='__main__':unittest.main()
