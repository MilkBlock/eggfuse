import unittest
from types import SimpleNamespace

import torch

from multirule_maintenance import Segments, units
from multirule_support import logits
from selective_kernel import SparseMap


class DiscoveryTests(unittest.TestCase):
    def test_observations_leave_full_template_support(self):
        net = SimpleNamespace(
            gate=torch.nn.Sequential(
                torch.nn.Linear(99, 16), torch.nn.Tanh(), torch.nn.Linear(16, 1)
            )
        )
        q = torch.zeros(32)
        keys = torch.zeros(4, 32)
        counts = torch.zeros(4, 4)
        counts[2] = 0.5
        mass = torch.tensor([0.0, 1.0, 1.0, 0.0])
        for arm in ("ce-base", "ce-count", "ce-support"):
            p = logits(net, (q, keys, counts, mass), arm).softmax(0)
            self.assertTrue(bool((p > 0).all()))
            self.assertAlmostEqual(float(p.detach().sum()), 1.0, places=6)
        torch.testing.assert_close(keys, torch.zeros_like(keys))

    @unittest.skipUnless(torch.backends.mps.is_available(), "Metal publication index")
    def test_retire_replace_and_reinsert(self):
        model = SimpleNamespace(mapping=SparseMap().to("mps"), variant="mixed-sparse")
        s = Segments(model, width=2)
        rows = {(100 + i, 2): (1, [47113 * i, 19]) for i in range(5)}
        s.publish([], rows.items())
        old = s.segments[2][2]
        del rows[100, 2]
        rows[101, 2] = (2, [21, 83])
        s.publish([(100, 2)], [((101, 2), rows[101, 2])])
        self.assertIs(old, s.segments[2][2])
        rows[100, 2] = (3, [1, 2])
        s.publish([], [((100, 2), rows[100, 2])])
        refs, _, idx = s.build(rows)
        actual = {}
        for rr, _, ii in s.segments.values():
            actual.update(units(ii, rr))
        self.assertEqual(units(idx, refs), actual)
        self.assertNotIn(((101, 2), 1), [k[0] for k in actual])
