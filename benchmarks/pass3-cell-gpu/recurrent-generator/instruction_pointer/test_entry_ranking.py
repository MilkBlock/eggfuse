import unittest

from entry_counterfactual import disjoint_batches
from train_entry_ranking import comparisons


class EntryRankingTest(unittest.TestCase):
    def test_unverified_and_equal_gain_are_not_negatives(self):
        pairs = set(comparisons({0: (0, 0), 1: (0, 3), 3: (0, 3), 4: (-1, 0)}))
        self.assertEqual(pairs, {(1, 0), (3, 0), (0, 4), (1, 4), (3, 4)})

    def test_competing_verified_instantiations_get_separate_native_replays(self):
        cases = [(1, (2, 3)), (2, (2, 4)), (3, (5, 6)), (4, (3, 7))]
        batches = disjoint_batches(cases)
        self.assertCountEqual([case for batch in batches for case in batch], cases)
        for batch in batches:
            tokens = [token for _, steps in batch for token in steps]
            self.assertEqual(len(tokens), len(set(tokens)))
