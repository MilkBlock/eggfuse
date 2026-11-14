import unittest
import numpy as np
from audit_device_match_readout import dynamic_metrics


class ReadoutCoverage(unittest.TestCase):
    def test_negative_majority_does_not_hide_missed_positive_work(self):
        truth=np.array([True,True,False,False,False,False])
        m=dynamic_metrics(truth,np.array([.6,.1,.7,.1,.1,.1]))
        self.assertEqual(m['true_positives'],1);self.assertEqual(m['false_positives'],1)
        self.assertEqual(m['false_negatives'],1);self.assertEqual(m['recall'],.5)
        self.assertEqual(m['precision'],.5)
        empty=dynamic_metrics(truth,np.zeros(6))
        self.assertEqual(empty['recall'],0);self.assertIsNone(empty['precision'])

    def test_missing_or_nonfinite_scores_rejected(self):
        with self.assertRaises(ValueError):dynamic_metrics([True],[np.nan])
        with self.assertRaises(ValueError):dynamic_metrics([True],[.1,.2])

if __name__=='__main__':unittest.main()
