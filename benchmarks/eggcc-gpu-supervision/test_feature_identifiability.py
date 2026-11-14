import copy
import unittest
from collections import Counter
import numpy as np
from audit_feature_identifiability import context, ceiling


class Identifiability(unittest.TestCase):
    def fixture(self):
        slot = dict(definition='query', sort=dict(kind='eq', name='E'))
        rule = dict(slots=[slot, copy.deepcopy(slot)], query=[], effects=[])
        recipe = dict(rules=[rule])
        capture = dict(rule=0, bindings=dict(
            slots=np.array([[10, 20]]), slot_roots=np.array([[10, 20]]),
            witness_rows=np.array([[7]]), witness_records=np.array([[0]])),
            witness=dict(rule=np.array([[0]]), slot_valid=np.ones((1, 1, 2), bool),
                slots=np.array([[[10, 20]]]), slot_roots=np.array([[[10, 20]]])))
        return capture, recipe

    def test_renaming_does_not_distinguish_context(self):
        c, r = self.fixture(); d = copy.deepcopy(c)
        for k in ('slots', 'slot_roots'):
            d['bindings'][k] += 100
            d['witness'][k] += 100
        d['bindings']['witness_rows'] += 90
        self.assertEqual(context(c, 0, r, {}), context(d, 0, r, {}))

    def test_relationship_change_is_visible_but_labels_are_not(self):
        c, r = self.fixture(); d = copy.deepcopy(c)
        d['target_eq_classes'] = np.array([[0, 0]])
        self.assertEqual(context(c, 0, r, {}), context(d, 0, r, {}))
        d['witness']['slot_roots'][0, 0, 1] = 10
        self.assertNotEqual(context(c, 0, r, {}), context(d, 0, r, {}))

    def test_incomplete_source_rejected(self):
        c, r = self.fixture(); c['witness']['slot_valid'][0, 0, 1] = False
        with self.assertRaises(ValueError): context(c, 0, r, {})

    def test_ceiling_counts_majority_per_observable_input(self):
        result = ceiling({'a': Counter({(0, 0): 3, (0, 1): 2}),
                          'b': Counter({(0, 1): 4})})
        self.assertEqual(result['samples'], 9)
        self.assertEqual(result['maximum_exact_samples'], 7)
        self.assertEqual(result['samples_in_conflicting_groups'], 5)
        self.assertIsNone(ceiling({})['maximum_fraction'])

if __name__ == '__main__': unittest.main()
