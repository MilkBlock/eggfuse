from collections import Counter
from types import SimpleNamespace as NS
from unittest import TestCase

import numpy as np

from cost_bake import CostBake
from cost_dependencies import dependencies


class CostBakeTests(TestCase):
    def make(self):
        owner = NS(count=Counter())
        obj = CostBake(owner, ())
        obj.active = True
        obj.selected = np.array([True, False])
        obj.cut = 2
        rows = [np.array([[9, 0, v] for v in vs]) for vs in ([1, 1], [1, 10], [1, 12, 1, 10])]
        banks = [NS(rows=r) for r in rows]
        return obj, NS(bank=lambda t: banks[t], roles={7: (0, 1, 2)})

    def test_mixed_old_and_fresh_preserve_per_prefix_posting_order(self):
        obj, mem = self.make()
        paths = np.array([[0, 0], [0, 1], [1, 0]])
        post = np.array([0, 3, 1, 2])
        win = (post, np.array([0, 0, 2]), np.array([4, 4, 2]))
        listing, lo, n = obj.window(mem, 7, (0, 1, 2), 2, paths, win, 10)
        self.assertEqual([listing[i : i + w].tolist() for i, w in zip(lo, n)], [[3, 1], [0, 3, 1, 2], [1, 2]])
        self.assertEqual(obj.owner.count["cost_index_positions"], 4)
        obj.window(mem, 7, (0, 1, 2), 2, paths, win, 10)
        self.assertEqual(obj.owner.count["cost_index_positions"], 4)

    def test_later_fresh_role_preserves_early_prefix_and_explicit_roots(self):
        obj, mem = self.make()
        window = (None, np.array([0]), np.array([2]))
        self.assertIs(obj.window(mem, 7, (0, 1, 2), 1, np.array([[0]]), window, 10), window)
        obj.cut = 0
        self.assertEqual(obj.roots(np.array([0, 1])).tolist(), [1])

    def test_function_dependency_supplies_uniqueness_only_with_all_rule_inputs(self):
        row = lambda cols, keys: {"columns": [{"slot": n} for n in cols], "key_columns": keys}
        rule = {
            "slots": [{"definition": "query"}] * 3,
            "interface": {"rows": [row([0, 1], [0]), row([1, 2], [0])]},
            "query": [],
        }
        self.assertEqual(dependencies(rule, 0), (True, 0))
        self.assertEqual(dependencies(rule, 1), (False, 0))
