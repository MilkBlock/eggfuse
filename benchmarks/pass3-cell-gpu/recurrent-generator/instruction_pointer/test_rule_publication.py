import io
import json
import unittest
from types import SimpleNamespace

import torch

from rule_publication import menu_codes, read_rule_frame
from trigger_execution import ExecutionTrace


class RuleStateTests(unittest.TestCase):
    def test_only_scheduled_entry_receives_its_own_lanes(self):
        world = SimpleNamespace(layouts=[[(0,)], [(1,)], [(1,), (0,)]])
        s = {"menu": [2, 0, 1], "rule_state": {0: (32, False), 1: (96, True)}}
        cache = torch.zeros(3, 32, requires_grad=True)
        v = menu_codes(world, s, cache, "both")
        torch.testing.assert_close(
            v[:, :2], torch.tensor([[1.0, 0.75], [0.0, 0.5], [1.0, 0.75]])
        )
        self.assertEqual(v.shape[0], 3)
        self.assertFalse(cache.detach().any())
        self.assertTrue(torch.isfinite(v.sum(1).log_softmax(0)).all())
        v.sum().backward()
        self.assertTrue((cache.grad == 1.0).all())
        with self.assertRaises(KeyError):
            menu_codes(world, dict(s, rule_state={0: (32, False)}), cache, "dirty")

    def test_reject_cross_run_epoch_order_or_watermark_skew(self):
        obs = json.dumps([5, 8, True, False, [[2, 5, False], [4, 7, True]]])
        frame = {"run": 5, "epoch": 8, "rules": [(2, 5), (4, 7)]}
        self.assertEqual(
            read_rule_frame(io.StringIO(obs), frame),
            ({2: (5, False), 4: (7, True)}, True),
        )
        for changed in (
            {"run": 6},
            {"epoch": 9},
            {"rules": [(4, 7), (2, 5)]},
            {"rules": [(2, 5), (4, 6)]},
            {"final_publication": True},
        ):
            with self.assertRaises(ValueError):
                read_rule_frame(io.StringIO(obs), frame | changed)

    def test_admission_stops_leave_unchecked_dimensions_unknown(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        w = SimpleNamespace(layouts=[[(0,)], [(0,), (0,)]], primitives=1)
        state = {
            "run": 1,
            "epoch": 1,
            "rule_state": {0: (0, False)},
            "check_dirty": True,
        }
        t = ExecutionTrace()
        t.entry(w, state, 1, (), (11, 2, 0, 0))
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "checks"
            path.write_text("1,11,0,1,1,0\n")
            t.finish(
                {"origins": [], "signed_external": [0], "signed_internal": [0]},
                path,
                set(),
            )
        self.assertEqual(
            [t.higher[11][k] for k in ("trigger", "binding", "guard", "effective_ops")],
            ["failed", "unknown", "unknown", 0],
        )
