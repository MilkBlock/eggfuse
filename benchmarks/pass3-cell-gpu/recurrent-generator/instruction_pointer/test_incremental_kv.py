import copy
import unittest
from types import SimpleNamespace

import torch

from actor import InstructionActor
from cell_kv_model import CellKV
from incremental_kv import InferenceCache


class CacheTest(unittest.TestCase):
    def setUp(self):
        torch.manual_seed(31)
        self.n = CellKV.__new__(CellKV)
        torch.nn.Module.__init__(self.n)
        self.n.actor = InstructionActor()
        self.n.arm = "C"
        self.n.read_ports_at_template = True
        self.n.cache = torch.randn(4, 32), torch.randn(2, 32), torch.randn(2, 32)
        self.n.eval()
        self.c = copy.deepcopy(self.n)
        self.w = SimpleNamespace()
        self.a = ((11, 0, 1), 11, -1, 0, (123,), False, ())
        self.b = ((12, 0, 2), 12, 0, 1, (456,), False, (self.a[0],))
        self.extra = ((12, 1, 2), 12, 0, 1, (), True, (self.a[0],))
        self.rs = ((1, 2, 0, (self.b[0], self.a[0]), (13, 0, 0, 3)),)

    @torch.no_grad()
    def test_incremental_values_and_response_visibility(self):
        cache = InferenceCache(self.c)
        newer = ((11, 0, 3), 11, -1, 0, (111,), True, ())
        appended = self.rs + ((1, 2, 1, (), (14, 1, 0, 0)),)
        for ep, ps, records in (
            (2, [self.a, self.b], self.rs),
            (2, [self.a, self.b], appended),
            (2, [self.extra, self.b], appended),
            (3, [newer, self.extra, self.b], appended),
            (4, [], appended),
        ):
            s = {
                "ports": ps,
                "request_receipts": records,
                "epoch": ep,
                "run": 1,
                "response": (0, 0, 0),
                "menu": [0, 1],
            }
            expected = self.n.state(self.w, s)
            actual = self.c.state(self.w, s)
            for k in ("lp", "keys", "ctx", "ext", "ek", "vals", "owners"):
                torch.testing.assert_close(actual[k], expected[k], rtol=1e-5, atol=1e-6)
            self.assertEqual(actual["refs"], [p[0] for p in ps])
        self.assertEqual(cache.count["receipt_headers_encoded"], 2)
        self.assertEqual(cache.count["public_view_hits"], 1)
        self.assertEqual(cache.count["payload_encoded"], 4)
        s["request_receipts"] = self.rs
        with self.assertRaisesRegex(ValueError, "diverged"):
            self.c.state(self.w, s)
        self.c.actor.query.weight.add_(0.01)
        with self.assertRaisesRegex(ValueError, "updated"):
            self.c.state(self.w, s)

    def test_training_cannot_attach(self):
        with self.assertRaisesRegex(ValueError, "frozen"):
            InferenceCache(self.c)
