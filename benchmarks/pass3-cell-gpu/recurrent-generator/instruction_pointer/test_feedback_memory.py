import unittest
from types import SimpleNamespace

import torch

from actor import InstructionActor
from cell_kv_model import CellKV
from cell_kv_runtime import Instances


class FeedbackMemoryTests(unittest.TestCase):
    def test_receipt_rows_are_not_port_publications(self):
        w = SimpleNamespace(menu=lambda _: [0])
        f = {
            "run": 1,
            "epoch": 3,
            "accepted": [],
            "updates": [],
            "retired": [],
            "rules": [],
        }
        m = Instances(w, True)
        ref = (-3, 0, 2)
        before = m.snapshot(w, f)
        for uid, reason in ((1, 0), (2, 1), (3, 8)):
            m.acknowledge(
                SimpleNamespace(run=1, epoch=3), 0, [ref], [uid, reason, -1, 0]
            )
        after = m.snapshot(w, f)
        self.assertEqual(before["request_receipts"], ())
        self.assertEqual(after["ports"], [])
        self.assertEqual([r[4][1] for r in after["request_receipts"]], [0, 1, 8])
        self.assertEqual(after["request_receipts"][0][3], (ref,))
        self.assertNotIn("request_receipts", Instances(w).snapshot(w, f))

    def test_receipt_changes_context_without_changing_address_support(self):
        torch.manual_seed(91)
        net = CellKV.__new__(CellKV)
        torch.nn.Module.__init__(net)
        net.actor = InstructionActor()
        net.arm = "C"
        net.read_ports_at_template = True
        net.cache = (torch.randn(4, 32), torch.randn(2, 32), torch.randn(1, 32))
        ref = (-3, 1, 1)
        s = {
            "run": 2,
            "epoch": 3,
            "response": (0, 1, 0),
            "ports": [(ref, -3, -1, 0, (33,), False, ())],
            "menu": [0, 1],
        }
        w = SimpleNamespace()
        a = net.state(w, s)
        b = net.state(w, dict(s, request_receipts=[(2, 3, 0, (ref,), (5, 0, -1, 0))]))
        c = net.state(w, dict(s, request_receipts=[(2, 3, 0, (ref,), (5, 8, -1, 0))]))
        self.assertEqual(b["refs"], [ref])
        self.assertEqual(a["pos"], c["pos"])
        torch.testing.assert_close(a["keys"], b["keys"])
        self.assertGreater(float((a["ctx"] - b["ctx"]).detach().norm()), 0)
        self.assertGreater(float((b["lp"] - c["lp"]).detach().norm()), 0)
