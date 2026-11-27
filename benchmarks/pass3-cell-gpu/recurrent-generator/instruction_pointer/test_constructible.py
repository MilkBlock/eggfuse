import unittest

import numpy as np
import torch

from competition_draw import Page
from selected_cell_model import constructible_roots


class ConstructibleTests(unittest.TestCase):
    def test_only_nonempty_declared_domains_condition_the_mass(self):
        logits = torch.tensor([1.0, 2.0, 3.0, 4.0], requires_grad=True)
        # Zero parents and repeated use of a single published port are both legal.
        lp, ok = constructible_roots(
            logits.log_softmax(0), [[], [4, 4], [4, 7], [7]], torch.tensor([4])
        )
        self.assertTrue(ok)
        torch.testing.assert_close(lp[:2].exp(), logits[:2].softmax(0))
        self.assertTrue(lp[2:].isneginf().all())
        (-lp[1]).backward()
        torch.testing.assert_close(logits.grad[2:], torch.zeros(2), atol=1e-6, rtol=0)
        self.assertGreater(float(logits.grad[0]), 0)

    def test_empty_memory_supports_only_zero_parent_rules(self):
        lp, ok = constructible_roots(
            torch.zeros(2), [[2], []], torch.empty(0, dtype=torch.long)
        )
        self.assertTrue(ok)
        torch.testing.assert_close(lp.exp(), torch.tensor([0.0, 1.0]))
        lp, ok = constructible_roots(
            torch.zeros(1), [[2]], torch.empty(0, dtype=torch.long)
        )
        self.assertFalse(ok)
        page = Page.__new__(Page)
        page.m = {"has_complete_domain": ok}
        self.assertEqual(page.draws(np.random.default_rng(12), 6, True), [])
        self.assertTrue(lp.isneginf().all())

    def test_same_types_under_permutation_and_replication(self):
        lp = torch.tensor([-1.0, -2.0, -3.0])
        roles = [[1, 2], [3], [2]]
        a, _ = constructible_roots(lp, roles, torch.tensor([1, 2]))
        b, _ = constructible_roots(lp, roles, torch.tensor([2, 1, 2, 1]))
        torch.testing.assert_close(a, b)
