import unittest
from types import SimpleNamespace

import torch
from torch import nn

from prefix_attention import attach, static_wires


class PrefixAttentionTest(unittest.TestCase):
    def fixture(self):
        def row(atom, slots):
            return {"atom": atom, "columns": [{"slot": i} for i in slots]}

        cat = SimpleNamespace(
            query_nodes={(0, i): i for i in range(3)},
            edges=[(3, 1, 4), (3, 2, 6), (4, 2, 4)],
            field_links={(0, 0, 1): [(0, 0)], (0, 0, 2): [(0, 1)], (0, 1, 2): [(1, 0)]},
        )
        w = SimpleNamespace(
            prog={
                "recipe": {
                    "rules": [
                        {
                            "interface": {
                                "rows": [row(0, [0]), row(1, [0, 1]), row(2, [1, 0])]
                            }
                        }
                    ]
                }
            },
            cat=cat,
            layouts=[[(0,)]],
        )
        role = nn.Linear(32, 32, bias=False)
        with torch.no_grad():
            role.weight.copy_(torch.eye(32))
        n = SimpleNamespace(
            actor=SimpleNamespace(latent=role, query=role, input_content=role),
            cache=(torch.zeros(5, 32), None, None),
            address=lambda w, m, t, p: torch.tensor(
                [-float("inf"), -float("inf"), 0.0, 0.0]
            ).log_softmax(0),
        )
        ports = [
            (None, None, None, None, r)
            for r in [(0,), (0, 2**64 - 1), (2**64 - 1, 0), (0, 0)]
        ]
        return w, attach(n), {"ports": ports}

    def test_two_bound_parents_score_one_candidate(self):
        w, n, m = self.fixture()
        self.assertEqual(static_wires(w, 0, 2), ((1, 1, 0, 4), (0, 0, 1, 3)))
        p = n.address(w, m, 0, (0, 1))
        self.assertGreater(p[2], p[3])
        self.assertEqual(p[:2].exp().sum(), 0)
        self.assertAlmostEqual(float(p.detach().exp().sum()), 1.0, places=5)
        (-p[3]).backward()
        self.assertGreater(float(n.actor.latent.weight.grad.norm()), 0)

    def test_first_parent_unchanged_and_no_hidden_partner(self):
        w, n, m = self.fixture()
        self.assertEqual(n.address(w, m, 0, ()).exp().tolist(), [0, 0, 0.5, 0.5])
        self.assertNotIn("prefix_bits", m)
        w.cat.field_links[0, 0, 1] = []
        self.assertEqual(n.address(w, m, 0, (0,)).exp().tolist(), [0, 0, 0.5, 0.5])
        self.assertNotIn("prefix_bits", m)
