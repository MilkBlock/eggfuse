import unittest
from types import SimpleNamespace

import torch

from selected_cell_model import SelectedCell, typed_distribution
from selected_cell_study import reason


class TestSelectedCell(unittest.TestCase):
    def test_static_type_support(self):
        logp = torch.log(torch.tensor([0.25, 0.1, 0.25, 0.4]))
        tables = torch.tensor([3, 7, 3, 7])
        self.assertIsNone(typed_distribution(logp, tables, 8))
        out = typed_distribution(logp, tables, 7)
        torch.testing.assert_close(out.exp(), torch.tensor([0, 0.2, 0, 0.8]))
        sampler = SimpleNamespace(typed=True)
        self.assertEqual(
            SelectedCell.sample(sampler, out, SimpleNamespace(random=lambda: 0.0)), 1
        )
        self.assertEqual(
            SelectedCell.sample(
                sampler, out, SimpleNamespace(random=lambda: 1.0 - 2**-53)
            ),
            3,
        )

    def test_attribution(self):
        ports = [((0, 0, 1), 0, -1, 3), ((0, 1, 1), 0, -1, 4), ((1, 0, 1), 1, -1, 4)]
        s = {"ports": ports}
        w = SimpleNamespace(layouts=[[(0, 0, ())]], roles=[[4, 3]])

        def classify(p):
            return reason(w, s, 0, (ports[1][0], ports[p][0]))

        self.assertEqual(classify(0), ("compatible", None))
        self.assertEqual(classify(1), ("wrong_port_on_compatible_owner", 1))
        self.assertEqual(classify(2), ("owner_without_declared_port", 1))
        w.roles[0][1] = 7
        self.assertEqual(classify(2), ("no_declared_type_in_memory", 1))

    def test_sampling_and_ce_share_the_zero_one_two_parent_factorization(self):
        import numpy as np

        class Toy(SelectedCell):
            def state(self, w, s):
                return s

            def variant_prob(self, w, m, rid, first):
                if rid == 1:
                    return (
                        torch.tensor([0.75, 0.25]).log()
                        if first == 0
                        else torch.tensor([0.25, 0.75]).log()
                    )
                return torch.zeros(1)

            def address(self, w, m, tid, prefix):
                return (
                    torch.tensor([0.6, 0.4]).log()
                    if not prefix
                    else torch.tensor([0.2, 0.8]).log()
                )

        net = Toy.__new__(Toy)
        torch.nn.Module.__init__(net)
        net.mode = "direct"
        net.typed = True
        refs = ((11, 0, 1), (12, 1, 2))
        w = SimpleNamespace(
            layouts=[[(r, 0, ())] for r in (0, 1, 2, 1)], roles=[[], [1], [1, 2]]
        )
        s = {
            "menu": [0, 1, 2, 3],
            "refs": refs,
            "pos": {r: i for i, r in enumerate(refs)},
            "memo": {},
            "families": {0: [0], 1: [1, 3], 2: [2]},
            "root_lp": torch.tensor([0.2, 0.3, 0.5]).log(),
        }
        from collections import Counter
        from itertools import product

        targets = [
            (t, rs)
            for t in s["menu"]
            for rs in product(refs, repeat=len(w.roles[w.layouts[t][0][0]]))
        ]
        ps = {tok: float((-net.token_loss(w, s, tok)).exp()) for tok in targets}
        self.assertAlmostEqual(sum(ps.values()), 1.0, places=6)
        self.assertAlmostEqual(ps[3, (refs[0],)], 0.3 * 0.6 * 0.25, places=6)
        self.assertAlmostEqual(ps[2, refs], 0.5 * 0.6 * 0.8, places=6)
        sampled = Counter(net.generate(w, s, np.random.default_rng(42), 4096))
        self.assertTrue(all(abs(sampled[t] / 4096 - ps[t]) < 0.025 for t in targets))
