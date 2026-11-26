import unittest
from collections import Counter

from credit_scale_fit import downstream, online_marginal
from credit_scale_programs import topology
from discrete_draft import Cell


class CreditTests(unittest.TestCase):
    def test_split_signature_erases_names_and_values_but_preserves_guard(self):
        first = "(rule ((P001 x) (< x 13)) ((P003 x)) :ruleset s0)"
        changed = "(rule ((P091 x) (< x 87)) ((P088 x)) :ruleset s0)"
        self.assertEqual(topology(first), topology(changed))
        self.assertNotEqual(topology(first), topology(changed.replace(" (< x 87)", "")))

    def test_conserved_shared_parent_credit(self):
        a = Cell(0, ())
        b = Cell(1, ((1, 0, 1), (1, 1, 1)))
        c = Cell(2, ((1, 0, 1), (2, 0, 2)))
        scores = downstream({1: a, 2: b, 3: c})
        self.assertEqual(scores, {1: 1.75, 2: 0.75, 3: 0.5})

    def test_unknown_not_penalized_and_new_action_paid_once(self):
        a, b, c = (Cell(i, ()) for i in range(3))
        _, score = online_marginal({a}, set(), {b}, {a: 1.25}, "downstream")
        self.assertEqual(score([a, b, c]), [1.25, -1, 0])
        self.assertEqual(score([a, a]), [-1, -1])

    def test_duplicate_feedback_is_marginal_for_complete_pages(self):
        a, b = Cell(0, ()), Cell(1, ())
        for xs in ([a, a, b], [a, b, b], [a, a, a]):
            _, marginal = online_marginal({a}, {b}, set(), {}, "duplicate")

            def reward(ds):
                return len(set(ds)) - sum(n - 1 for n in Counter(ds).values())

            self.assertEqual(
                marginal(xs),
                [reward(xs) - reward(xs[:i] + xs[i + 1 :]) for i in range(len(xs))],
            )
