"""Regression checks for feature identity, sparse sampling and publication ownership."""

import unittest
from collections import Counter

import numpy as np
import torch

from foundation_diagnostics import Fixture
from foundation_memory import AssociationMemory
from selective_kernel import SparseMap
from shared_posting import FieldPostings, propose, same_row_score


class PostingTest(unittest.TestCase):
    def setUp(self):
        self.m = Fixture(4, 2, 1)
        self.mapping = SparseMap().eval()
        self.mem = FieldPostings(self.mapping, "cpu")
        self.st = Counter()

    def publish(self, updates, retired=()):
        self.mem.publish(self.m, dict(updates=updates, retired=retired), self.st)

    def test_shared_row_and_sampling(self):
        # Rows 1 and 2 match different marginals. Only row 3 preserves both.
        for (_, r), vals in zip(
            self.m.up, [(1, 2), (1, 2**64 - 2), (2**64 - 3, 2), (1, 2)]
        ):
            r["hashes"] = list(vals)
        self.publish(self.m.up)
        bank = self.mem.banks[0]
        wires = [(bank, torch.tensor([0]), c, c) for c in (0, 1)]
        score = same_row_score(bank, torch.tensor([[1, 2, 3]]), wires)
        self.assertGreater(score[0, 2], score[0, :2].max())
        # An independent dense computation only in this test, including collisions.
        rng = np.random.default_rng(42)
        u = torch.from_numpy(rng.random((1, 40000, 5), dtype=np.float32))
        got = propose(bank, wires, u).flatten().bincount(minlength=4) / 40000
        mass = torch.zeros(4)
        for c in (0, 1):
            for h in range(4):
                for r in range(4):
                    sx, tx = c, 2 * r + c
                    for a in (0, 1):
                        for b in (0, 1):
                            if bank.lo[sx, h] + a == bank.lo[tx, h] + b:
                                x, y = bank.frac[sx, h], bank.frac[tx, h]
                                mass[r] += (x if a else 1 - x) * (y if b else 1 - y)
        expected = 0.95 * mass / mass.sum() + 0.05 / 4
        torch.testing.assert_close(got, expected, rtol=0, atol=0.012)

    def test_retire_republish_and_ragged(self):
        self.m.up[1][1]["hashes"] = []
        self.publish(self.m.up)
        self.m.up[2][1].update(version=2, hashes=[987])
        self.publish([self.m.up[2]], [self.m.up[0][0]])
        self.assertNotIn((0, 0), self.mem.loc)
        bank = self.mem.banks[0]
        self.assertNotIn((2, 0, 1), bank.refs)
        self.assertIn((2, 0, 2), bank.refs)
        self.assertEqual(self.st["fields_encoded"], 7)
        row = torch.arange(len(bank.refs))
        u = torch.rand(3, 8, 5)
        wires = [(bank, row, 1, 1)]
        ids = propose(bank, wires, u)
        self.assertTrue(torch.isfinite(same_row_score(bank, ids, wires)).all())
        self.assertLess(int(ids.max()), len(bank.refs))
        self.publish([], [self.m.up[i][0] for i in (1, 2, 3)])
        self.assertFalse(self.mem.banks or self.mem.loc)

    def test_lossy_bins_do_not_certify_field_equality(self):
        # Flip a bit outside all four projection heads in the actual map.
        used = set(self.mapping.coords.flatten().tolist())
        bit = next(i for i in range(64) if i not in used)
        x, y = 71, 71 ^ (1 << bit)
        self.assertNotEqual(x, y)
        lo, frac = self.mem.encode([x, y])
        torch.testing.assert_close(lo[0], lo[1])
        torch.testing.assert_close(frac[0], frac[1])

    def test_relocation_to_an_existing_table(self):
        self.m.up[0][1]["table"] = 1
        self.publish(self.m.up)
        self.m.up[1][1].update(table=1, version=2)
        self.publish(self.m.up[1:2], [self.m.up[1][0]])
        tab, idx = self.mem.loc[1, 0]
        self.assertEqual((tab, self.mem.banks[tab].refs[idx]), (1, (1, 0, 2)))
        self.assertNotIn((1, 0, 1), self.mem.banks[0].refs)

    def test_catalog_growth_keeps_existing_postings(self):
        from types import SimpleNamespace
        from torch import nn
        from shared_posting import SparseCompletion

        mdl = SimpleNamespace(
            local=SimpleNamespace(base=nn.Identity()), mapping=self.mapping
        )
        dec = SparseCompletion(mdl, "cpu")
        m = Fixture(12, 3, 8)
        ids = m.ids
        m.ids = ids[:1]
        dec.publish(
            m,
            {"recipe": {"rules": m.prog["recipe"]["rules"][:1]}},
            dict(updates=m.up, retired=[]),
            self.st,
        )
        before = self.st.copy()
        bank = dec.mem.banks[0]
        m.ids = ids
        dec.publish(m, m.prog, dict(updates=[], retired=[]), self.st)
        self.assertIs(bank, dec.mem.banks[0])
        self.assertEqual(self.st, before)
        self.assertEqual(len(dec.schemas), 8)

    def test_dense_compaction_shares_physical_storage(self):
        active = []
        for compact in (False, True):
            mem = AssociationMemory(self.mapping, "cpu", 2, compact=compact)
            mem.publish(self.m, dict(updates=self.m.up, retired=[]), Counter())
            for page in mem.pages.values():
                key = mem.lookup(page.refs[0])[1]
                self.assertEqual(
                    key.untyped_storage()._cdata == page.keys.untyped_storage()._cdata,
                    compact,
                )
            active.append(mem)
        self.assertLess(active[1].bytes(), active[0].bytes())
        for key in active[0].rows:
            ref = active[0].rows[key][1]
            torch.testing.assert_close(
                active[0].lookup(ref)[2], active[1].lookup(ref)[2]
            )


if __name__ == "__main__":
    unittest.main()
