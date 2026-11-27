import math
import unittest
from types import SimpleNamespace

import torch

import test_prefix_attention as fixtures
from cell_kv_model import owner_reduce
from joint_cell_live import classify
from joint_cell_probabilities import decomposition
from joint_cell_sweep import complete_ce
from joint_cell_train import feedback


class JointTests(unittest.TestCase):
    def test_owner_reduction_payload_and_weight_gradients(self):
        gen = torch.Generator().manual_seed(3)
        logits = torch.randn(
            3, 6, generator=gen, dtype=torch.float64, requires_grad=True
        )
        payload = torch.randn(
            3, 6, 4, generator=gen, dtype=torch.float64, requires_grad=True
        )
        group = torch.tensor([2, 0, 1, 0, 2, 0])
        truth = torch.stack(
            [
                torch.einsum(
                    "qp,qpd->qd",
                    logits[:, group == i].softmax(1),
                    payload[:, group == i],
                )
                for i in range(3)
            ],
            1,
        )
        got = owner_reduce(logits, payload, group, 3)
        torch.testing.assert_close(got, truth)
        a = torch.autograd.grad(truth.square().sum(), (logits, payload))
        b = torch.autograd.grad(got.square().sum(), (logits, payload))
        for g, h in zip(a, b, strict=True):
            torch.testing.assert_close(g, h)

    def test_future_role_uses_public_unbound_values_and_no_mask(self):
        w, n, m = fixtures.PrefixAttentionTest().fixture()
        w.roles = [[10, 11, 12]]
        m["ports"][1] = (None, None, None, None, (0, 0))
        m.update(tables=torch.tensor([11, 12, 10, 10]), ctx=torch.zeros(32))
        feedback(n)
        lp = n.address(w, m, 0, ())
        self.assertEqual(lp.isfinite().tolist(), [False, False, True, True])
        self.assertAlmostEqual(float(lp.exp().sum().detach()), 1.0, places=5)
        self.assertGreater(abs(float((lp[2] - lp[3]).detach())), 1e-3)
        (-lp[2]).backward()
        self.assertGreater(float(n.actor.latent.weight.grad.norm()), 0.0)

    def test_named_repetitions_preserve_new_versions(self):
        def row(i, run, v, gain, reason):
            return dict(
                uid=i,
                run=run,
                tid=2,
                rid=2,
                refs=((11, 1, v),),
                effective_ops=gain,
                status=reason,
            )

        entries = {
            r["uid"]: r
            for r in (
                row(1, 1, 0, 1, "accepted"),
                row(2, 1, 0, 0, "duplicate"),
                row(3, 2, 0, 1, "accepted"),
                row(4, 2, 1, 0, "duplicate"),
            )
        }
        stats, rows = classify([[1, 2], [3, 4]], entries)
        self.assertEqual(
            [r["kind"] for r in rows],
            ["first_name", "same_page", "cross_submit", "first_name"],
        )
        self.assertEqual(stats["changed_run_repeat_productive"], 1)
        self.assertEqual(stats["native_duplicate_new_refs"], 1)

    def test_log_factorisation(self):
        d = decomposition(
            [math.log(0.8), math.log(0.2)], [math.log(0.4), math.log(0.3)]
        )
        self.assertAlmostEqual(d["log_change"], math.log(0.12 / 0.16))
        self.assertEqual(d["largest_loss"], 0)

    def test_complete_ce_shares_actual_prefix(self):
        w = SimpleNamespace(layouts=[[(0,)]])
        m = dict(
            pos={11: 0, 12: 1}, families={0: [0]}, menu=[0], root_lp=torch.zeros(1)
        )
        x = torch.tensor([-0.5, 0.4], requires_grad=True)
        calls = []

        def address(w, m, r, p):
            calls.append(p)
            return x.log_softmax(0)

        n = SimpleNamespace(address=address, variant_prob=lambda *args: torch.zeros(1))
        ts = [(0, (11, 12)), (0, (11, 11))]
        loss = complete_ce(n, w, m, ts)
        self.assertEqual(calls, [(), (0,)])
        lp = x.log_softmax(0)
        ref = -(3 * lp[0] + lp[1]) / 2
        torch.testing.assert_close(loss, ref)
        torch.testing.assert_close(
            torch.autograd.grad(loss, x)[0], torch.autograd.grad(ref, x)[0]
        )
