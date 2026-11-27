import unittest
from types import SimpleNamespace

import numpy as np
import torch

from competition_draw import Page
from variable_completion import boundary_input, label


class VariableCompletionTests(unittest.TestCase):
    def page(self):
        model = SimpleNamespace(
            state=lambda *_: {
                "families": {0: [0], 1: [1]},
                "menu": [0, 1],
                "root_lp": torch.full((2,), -np.log(2)),
                "refs": [],
            },
            variant_prob=lambda *_: torch.zeros(1),
        )
        return Page(model, SimpleNamespace(roles=[[], []]), {})

    def test_end_does_not_emit_or_exhaust_next_page(self):
        p = self.page()
        rng = np.random.default_rng(13)
        self.assertEqual(p.draws(rng, 4, True, 1), [])
        self.assertTrue(p.ended)
        self.assertEqual(set(p.draws(rng, 4, True, 0)), {(0, ()), (1, ())})
        self.assertFalse(p.ended)
        self.assertEqual(len(p.draws(rng, 4, False, 0)), 4)

    def test_residual_named_mass(self):
        p = self.page()
        rng = np.random.default_rng(31)
        lengths = (
            np.bincount(
                [len(p.draws(rng, 2, True, 0.2)) for _ in range(10000)], minlength=3
            )
            / 10000
        )
        # P(one Cell then END) = .8 * .2/(.2+.8*.5).
        np.testing.assert_allclose(lengths, [0.2, 0.8 / 3, 0.8 * 2 / 3], atol=0.015)

    def test_end_requires_positive_proof_of_inactive_scope(self):
        w = SimpleNamespace(roles=[[], [6]], layouts=[[(0,)], [(1,)], [(1,)]])
        s = {
            "ports": [],
            "menu": [0, 1, 2],
            "rule_state": {0: (1, False), 1: (0, True)},
            "check_dirty": True,
        }
        self.assertEqual(label(w, s, []), "end")
        self.assertEqual(label(w, dict(s, check_dirty=False), []), "unknown")
        self.assertEqual(label(w, dict(s, menu=[1, 2]), []), "unknown")
        self.assertEqual(
            label(w, dict(s, ports=[(None, None, None, 6)]), []), "unknown"
        )
        self.assertEqual(label(w, s, [(0, ())]), "cell")

    def test_boundary_uses_existing_family_distribution(self):
        m = {
            "ctx": torch.tensor([3.0, 0.0]),
            "families": {4: [0, 1], 9: [2]},
            "root_lp": torch.tensor([0.25, 0.75]).log(),
            "score_codes": torch.tensor([[2.0, 0.0], [7.0, 8.0], [0.0, 4.0]]),
        }
        torch.testing.assert_close(boundary_input(m), torch.tensor([3.5, 3.0]))
