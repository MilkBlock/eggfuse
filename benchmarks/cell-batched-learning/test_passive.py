import unittest
from passive import maximal, select, prepare
from pathlib import Path


def fragment(hops, root=0):
    return {'root': root, 'hops': [{'source_frame': 0, 'rule': r, 'entry': e, 'op': 0} for r, e in hops]}


def row(f, births=3, inputs=9, cost=2):
    return {'fragment': f, 'observed': {'matched_births': births, 'available_shared_inputs': inputs},
            'static_instruction_handles': cost}


class PassiveSelectionTests(unittest.TestCase):
    def test_invalid_batch_budgets_fail_before_reading_inputs(self):
        for budgets in ((), (0,), (4097,)):
            with self.assertRaises(ValueError):
                prepare(Path("missing-audit-root"), budgets)

    def test_seed_language_survives_longer_paths(self):
        a, b, c = fragment([(1, 0)]), fragment([(1, 0), (2, 0)]), fragment([(8, 0)], root=1)
        selected, chosen = select([a, c], [row(b)], 1)
        self.assertEqual(selected, [c, b])
        self.assertEqual(len(chosen), 1)
        self.assertEqual(maximal([a, b, c]), [b, c])

    def test_alternative_anchors_do_not_consume_two_places(self):
        a, b = fragment([(1, 0)]), fragment([(1, 1)])
        selected, chosen = select([], [row(a, inputs=5), row(b, inputs=10)], 5)
        self.assertEqual(selected, [b])
        self.assertEqual(len(chosen), 1)

    def test_unobserved_or_no_shared_input_is_not_admitted(self):
        selected, chosen = select([], [row(fragment([(1, 0)]), births=1),
                                       row(fragment([(2, 0)]), inputs=0)], 5)
        self.assertEqual((selected, chosen), ([], []))

    def test_budget_does_not_discard_seed(self):
        seed = fragment([(1, 0)])
        selected, chosen = select([seed], [row(fragment([(2, 0)]))], 0)
        self.assertEqual(selected, [seed])
        self.assertFalse(chosen)


if __name__ == '__main__':
    unittest.main()
