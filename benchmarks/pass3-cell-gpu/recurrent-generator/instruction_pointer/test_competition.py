import unittest
from collections import Counter
from types import SimpleNamespace

import numpy as np
import torch

from competition_draw import Page


class Toy:
    def state(self, w, state):
        return {
            "families": {0: [0], 1: [1, 2], 2: [3]},
            "menu": [0, 1, 2, 3],
            "refs": [(41, 0, 7), (68, 0, 9)],
            "root_lp": torch.tensor([0.3, 0.5, 0.2], dtype=torch.float64).log(),
        }

    def variant_prob(self, w, m, rid, first):
        if rid == 1:
            return torch.tensor([0.8, 0.2] if first == 0 else [0.2, 0.8]).log()
        return torch.zeros(1)

    def address(self, w, m, tid, prefix):
        return None if tid == 2 else torch.tensor([0.7, 0.3]).log()


class CompetitionTests(unittest.TestCase):
    def test_complete_token_sampling_and_empty_root(self):
        page = Page(Toy(), SimpleNamespace(roles=[[], [4], [9]]), {})
        traces = [page.draws(np.random.default_rng(i), 2, True) for i in range(6000)]
        zero = (0, ())
        hist = Counter(tok[1] for tok in traces if tok[0] == zero)
        self.assertNotIn(zero, hist)
        # Conditional next draw after zero includes the unsuccessful .2 mass.
        self.assertAlmostEqual(hist[None] / hist.total(), 0.2 / 0.7, delta=0.035)
        self.assertAlmostEqual(
            hist[(1, ((41, 0, 7),))] / hist.total(), 0.5 * 0.7 * 0.8 / 0.7, delta=0.035
        )
        out = page.draws(np.random.default_rng(7781), 256, True)
        valid = [t for t in out if t is not None]
        self.assertEqual(len(valid), 5)
        self.assertEqual(len(set(valid)), 5)
        self.assertIn(None, out)
        hist = Counter(page.draws(np.random.default_rng(90), 10000, False))
        self.assertAlmostEqual(hist[zero] / hist.total(), 0.3, delta=0.025)

    def test_exhaustion_and_page_reset(self):
        toy = Toy()
        toy.state = lambda w, s: {
            "families": {0: [0]},
            "menu": [0],
            "refs": [],
            "root_lp": torch.zeros(1),
        }
        page = Page(toy, SimpleNamespace(roles=[[]]), {})
        for seed in (1, 2):
            self.assertEqual(
                page.draws(np.random.default_rng(seed), 16, True), [(0, ())]
            )
