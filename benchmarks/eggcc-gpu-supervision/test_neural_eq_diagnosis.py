import unittest
from neural_eq_diagnosis import diagnose


class Diagnosis(unittest.TestCase):
    def test_transitive_false_merge_and_external_missing(self):
        result=diagnose([1,-1,1],[1,0,0],[1,1,1],[1,0,0],3)
        self.assertTrue(result['has_false_merge'])
        self.assertEqual([p['slots'] for p in result['pairs']],[[0,2],[1,2]])
        result=diagnose([-1],[1],[1],[0],2)
        self.assertTrue(result['has_external_missing'])
        self.assertFalse(result['has_false_merge'])

    def test_mask_and_nonfinite(self):
        self.assertIsNone(diagnose([1],[0],[0],[0],2))
        result=diagnose([float('nan')],[0],[1],[0],2)
        self.assertIsNone(result['pairs'][0]['raw_score'])


if __name__=='__main__':unittest.main()
