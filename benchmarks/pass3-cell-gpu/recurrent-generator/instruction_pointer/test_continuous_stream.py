import unittest
from types import SimpleNamespace

import numpy as np
import torch

from competition_draw import Page
from continuous_stream import Stream, named_path
from test_competition import Toy


class Network(Toy):
    def state(self, w, s):
        m = super().state(w, s)
        m["pos"] = {ref: i for i, ref in enumerate(m["refs"])}
        return m


class ContinuousTests(unittest.TestCase):
    def setUp(self):
        self.w = SimpleNamespace(
            roles=[[], [0], [1]], layouts=[[(i,)] for i in (0, 1, 1, 2)]
        )
        self.n = Network()

    def test_discount_changes_only_one_complete_name(self):
        page = Page(self.n, self.w, {})
        adjusted = {}
        root = ("root", None, None, ())
        path = named_path(page, (1, ((41, 0, 7),)))
        page.set_leaf_factor(path, adjusted, 0.25)
        self.assertAlmostEqual(
            adjusted[root].sum(), 1 - 0.75 * 0.5 * 0.7 * 0.8, places=6
        )
        other = named_path(page, (2, ((41, 0, 7),)))
        page.set_leaf_factor(other, adjusted, 0.0)
        self.assertAlmostEqual(
            adjusted[root].sum(), 1 - 0.75 * 0.5 * 0.7 * 0.8 - 0.5 * 0.7 * 0.2, places=6
        )
        self.assertIsNone(named_path(page, (1, ((41, 0, 8),))))

    def test_view_and_receipt_reentry_even_if_only_one_name(self):
        w = SimpleNamespace(roles=[[]], layouts=[[(0,)]])
        self.n.state = lambda w, s: {
            "menu": [0],
            "families": {0: [0]},
            "root_lp": torch.zeros(1),
            "refs": [],
            "pos": {},
        }
        for mode in ("B", "C"):
            p = Stream(self.n, mode)
            rng = np.random.default_rng(12)
            s = {"menu": [0], "request_receipts": ()}
            self.assertEqual(p.generate(w, s, rng, 2), [(0, ())])
            self.assertEqual(p.generate(w, s, rng, 2), [])
            self.assertEqual(
                p.generate(w, dict(s, request_receipts=(1,)), rng, 2), [(0, ())]
            )
            # Same receipt count after a new publication must invalidate the cache.
            p.observe_publication({})
            self.assertEqual(
                p.generate(w, dict(s, request_receipts=(1,)), rng, 2), [(0, ())]
            )
            self.assertEqual(p.count["exact_view_reuse"], 1)
