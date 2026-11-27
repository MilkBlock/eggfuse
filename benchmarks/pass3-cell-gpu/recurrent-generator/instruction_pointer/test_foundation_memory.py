import itertools
import unittest
from collections import Counter
from types import SimpleNamespace

import torch

from discrete_draft import Cell
from foundation_completion import Completion
from foundation_diagnostics import Fixture
from foundation_study import packet_loss
from selective_kernel import SparseMap


class FoundationTest(unittest.TestCase):
    def setUp(self):
        torch.manual_seed(228)
        base = torch.nn.Module()
        for attr in ("scorer", "gate"):
            setattr(
                base,
                attr,
                torch.nn.Sequential(
                    torch.nn.Linear(99, 16), torch.nn.Tanh(), torch.nn.Linear(16, 1)
                ),
            )
        model = SimpleNamespace(local=SimpleNamespace(base=base), mapping=SparseMap())
        self.d = Completion(model, "evidence", "cpu", width=2)
        self.m = Fixture(3, 2, 2)
        self.m.roles[1] = ()
        self.m.enc.cat.inputs["generated", 1] = []
        self.m.prog["recipe"]["rules"][1]["interface"]["rows"] = []
        self.stats = Counter()
        self.d.publish(
            self.m, self.m.prog, {"retired": [], "updates": self.m.up}, self.stats
        )

    def test_complete_token_marginal_both_orders(self):
        refs = [(i, 0, 1) for i in range(3)]
        tokens = [Cell(0, x) for x in itertools.product(refs, repeat=2)] + [Cell(1, ())]
        for mode in ("evidence", "rule"):
            probs = []
            for cell in tokens:
                paths = self.d.paths(cell)
                loss = packet_loss(self.d.net, [(cell, paths)], mode, "cpu")
                probs.append((-loss).exp().item())
            self.assertAlmostEqual(sum(probs), 1, places=5)
            self.assertTrue(min(probs) > 0)

    def test_published_state_versions_and_catalog_growth(self):
        key = (0, 0)
        with self.assertRaises(ValueError):
            self.d.mem.lookup((*key, 0))
        before = self.d.mem.bytes()
        field = self.d.mem.lookup((*key, 1))[2]
        self.m.roles.append(self.m.roles[0])
        self.m.ids.append((2, False))
        self.m.prog["recipe"]["rules"].append(self.m.prog["recipe"]["rules"][0])
        self.m.enc.cat.inputs["generated", 2] = [0, 1]
        self.d.publish(self.m, self.m.prog, {"retired": [], "updates": []}, self.stats)
        self.assertEqual(before, self.d.mem.bytes())
        self.assertEqual(self.stats["rows_encoded"], 3)
        self.assertIs(field, self.d.mem.lookup((*key, 1))[2])
        rec = dict(self.m.up[0][1], version=2)
        self.m.pub.live[key] = (rec, None)
        self.d.publish(
            self.m,
            self.m.prog,
            {"updates": [(self.m.up[0][0], rec)], "retired": [self.m.up[1][0]]},
            self.stats,
        )
        self.assertEqual(self.d.mem.lookup((*key, 2))[2].shape, field.shape)
        with self.assertRaises(ValueError):
            self.d.mem.lookup((*key, 1))
        with self.assertRaises(KeyError):
            self.d.mem.lookup((1, 0, 1))

    def test_joint_fields_belong_to_one_row(self):
        # Exactly the same column marginals. Only the first row of the aligned
        # pair has both desired fields. Read the deployed row-choice bias.
        m, d = self.m, self.d
        ref = (0, 0, 1)

        def contrasts(pairs):
            updates = []
            for i, values in enumerate(pairs):
                rec = dict(m.up[i][1], hashes=values)
                m.pub.live[i, 0] = (rec, None)
                updates.append((m.up[i][0], rec))
            d.publish(m, m.prog, {"updates": updates, "retired": []}, self.stats)
            path = d.paths(Cell(0, (ref, (1, 0, 1))))[0]
            return path[-1][0].bias.detach().numpy()

        # All three rows must be in one physical page for this diagnostic.
        d.mem.width = 8
        from foundation_memory import AssociationMemory

        d.mem = AssociationMemory(SparseMap(), "cpu", width=8)
        aligned = contrasts([[1, 7], [1, 7], [95, 162]])
        crossed = contrasts([[1, 7], [1, 162], [95, 7]])
        self.assertGreater(aligned[1], max(crossed[1:]))
