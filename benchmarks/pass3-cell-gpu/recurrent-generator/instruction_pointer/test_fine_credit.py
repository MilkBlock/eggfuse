import json
import os
import unittest
from pathlib import Path

import torch

from discrete_draft import Cell
from fine_credit import labels, one_edit
from fine_fit import scope_loss
from transition_credit import comparable


class ReceiptCreditTests(unittest.TestCase):
    def test_trigger_checks_precede_all_binding_checks(self):
        for at_generation, scope in (
            (False, "template_at_generation"),
            (True, "submit_after_window"),
            (None, "issue_trigger_only"),
        ):
            credit = labels("untriggered_rule", at_generation, False, 0, False)
            self.assertEqual(set(credit), {"cost", "timing"})
            self.assertEqual(credit["timing"][0], scope)
        with self.assertRaises(ValueError):
            labels("untriggered_rule", True, True, 0, False)

    def test_guard_and_watermark_follow_binding(self):
        for verdict in ("guard", "watermark", "unbound_primitive"):
            v = labels(verdict, True, True, 0, False)
            self.assertEqual(v["binding"][1], 1)
            self.assertNotIn("contribution", v)
            self.assertNotIn("structure", v)
        self.assertNotIn("condition", labels("watermark", True, True, 0, False))
        self.assertNotIn("binding", labels("pending_port", True, None, 0, False))

    def test_duplicate_scopes_and_unknown(self):
        self.assertNotIn("novelty", labels("accepted", True, True, 0, False))
        self.assertEqual(
            labels("accepted", True, True, 0, True)["novelty"][0],
            "published_single_effect",
        )
        self.assertEqual(
            labels("duplicate", True, True, 0, False)["novelty"][0],
            "native_signing_key",
        )
        self.assertNotIn("dependency", labels("accepted", True, True, 2, False))
        self.assertNotIn("condition", labels("binding", True, True, 0, False))

    def test_substitution_and_owner_scope(self):
        a, b, c = ((-1, 0, 1), (-3, 1, 1), (1, 0, 1))
        src = Cell(4, (a, b))
        dst = Cell(4, (a, c))
        self.assertEqual(
            list(one_edit([src], [dst, Cell(3, (a, c)), Cell(4, (b, c)), src])),
            [(src, dst, 1)],
        )
        self.assertTrue(comparable(src, (1, 0), (2, 1)))
        self.assertFalse(comparable(dst, (1, 0), (2, 1)))
        self.assertFalse(comparable(Cell(4, ((-2, 0, 1),)), (1, 0), (2, 1)))

    def test_substitution_preserves_observation_and_arity(self):
        first = Cell(1, ((-1, 0, 1),), observe=1)
        self.assertEqual(
            list(one_edit([first], [Cell(1, ((-3, 0, 1),)), Cell(1, (), observe=1)])),
            [],
        )

    def test_scope_gradients_on_decision_factors(self):
        c = Cell(0, ((-1, 0, 1), (-2, 0, 1)))
        row = {
            "self_positive": set(),
            "positive": {},
            "negative": {c},
            "inactive": {c},
            "bad_binding": set(),
        }
        x = torch.tensor([[0.5, 0.2, 0.3]], requires_grad=True)
        scope_loss(x, {c: 0}, row, 4, "B").backward()
        self.assertEqual(x.grad.tolist(), [[1, 0, 0]])
        x.grad = None
        row.update(inactive=set(), bad_binding={c})
        scope_loss(x, {c: 0}, row, 4, "B").backward()
        self.assertEqual(x.grad[0, 0].item(), 0)
        self.assertTrue(torch.all(x.grad[0, 1:] > 0))

    @unittest.skipUnless(
        os.environ.get("FINE_CREDIT_OUTPUT"), "requires native paired replay"
    )
    def test_native_boundaries(self):
        folder = Path(os.environ["FINE_CREDIT_OUTPUT"])
        controls = json.loads((folder / "native-controls.json").read_bytes())
        cases = [
            next(x for x in controls[b] if x["run"] == 4)
            for b in ("empty", "left", "full", "cleared")
        ]
        self.assertEqual([x["gain"] for x in cases], [2, 1, 0, 2])
        self.assertTrue(
            all(
                (x["rule"], x["refs"]) == (cases[0]["rule"], cases[0]["refs"])
                for x in cases
            )
        )
        late = controls["delayed_draft"]
        self.assertEqual(
            labels(
                late["issued"]["status"],
                late["generate_dirty"],
                late["issue_dirty"],
                0,
                False,
            )["timing"][0],
            "submit_after_window",
        )
        port = json.loads((folder / "port-controls.json").read_bytes())
        self.assertEqual(
            [r["status"] for r in port if r["run"] == 3], ["version", "accepted"]
        )
        self.assertEqual(
            [r["status"] for r in port if r["run"] == 4], ["accepted", "pending_port"]
        )
        self.assertTrue(any(r["run"] == 5 and r["gain"] for r in port))
        higher = json.loads((folder / "higher-control.json").read_bytes())
        self.assertEqual([v["gain"] for v in higher], [2, 1, 0])
        self.assertEqual([v["completed"] for v in higher], [1, 1, 1])
        self.assertTrue(
            all(
                x["entry"] == higher[0]["entry"]
                and x["template"] == higher[0]["template"]
                for x in higher
            )
        )


if __name__ == "__main__":
    unittest.main()
