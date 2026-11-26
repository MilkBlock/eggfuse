import json
import os
import unittest
from pathlib import Path

from control_credit_allocation import allocation_target
from control_credit_experience import load, records
from control_credit_ledger import target
from control_credit_pairs import preference
from execution_control import CONTINUE, SEAL


class ControlCreditTests(unittest.TestCase):
    def test_empty_yield_is_unknown(self):
        zero = {
            "same_schedule": True,
            "ops": 0,
            "seal_hash": "a",
            "continue_hash": "a",
            "gained": [],
            "lost": [],
        }
        self.assertIsNone(preference(zero, zero, False, True))
        self.assertEqual(preference(zero, zero, True, True), SEAL)
        self.assertIsNone(preference(zero, zero, True, False))
        self.assertIsNone(
            preference(zero, dict(zero, continue_hash="other"), True, True)
        )

    def test_positive_requires_terminal_evidence(self):
        d = {"same_schedule": True, "ops": 1, "seal_hash": "a", "continue_hash": "b"}
        self.assertIsNone(preference(d, dict(d, gained=[], lost=[]), False, True))
        self.assertIsNone(preference(d, dict(d, gained=[14], lost=[9]), False, True))
        self.assertEqual(
            preference(d, dict(d, gained=[14], lost=[]), False, True), CONTINUE
        )

    def test_reconcile_choices(self):
        self.assertIsNone(target([]))
        self.assertIsNone(target([{"target": SEAL}, {"target": None}]))
        self.assertEqual(target([{"target": SEAL}, {"target": CONTINUE}]), CONTINUE)
        self.assertEqual(
            allocation_target({"same_schedule": True, "gained": [], "lost": [1]}, True),
            SEAL,
        )
        self.assertIsNone(
            allocation_target({"same_schedule": True, "gained": [], "lost": [1]}, False)
        )

    @unittest.skipUnless(
        os.getenv("CONTROL_CREDIT_OUTPUT"), "native experiment archives"
    )
    def test_native_identity_and_credit_scope(self):
        root = Path(os.environ["CONTROL_CREDIT_OUTPUT"])
        name = "neural-0000.json.gz"
        sh = load(root, "ledger", name)
        allocation = load(root, "allocation", name)
        self.assertTrue(all(r["accounted"] for r in allocation["delays"]))
        self.assertTrue(all(r["receipts_accounted"] for r in allocation["records"]))
        for r in records(sh, allocation):
            if r["kind"] == "cell":
                self.assertNotIn("allocation", r["credit"])
                self.assertNotIn("omission", r["credit"])
            else:
                self.assertNotIn("binding", r["credit"])
                self.assertNotIn("structure", r["credit"])
        probe = json.loads((root / "port-controls.json").read_bytes())
        self.assertTrue(any(r["status"] == "pending_port" for r in probe))
        self.assertTrue(any(r["run"] == 5 and r["gain"] > 0 for r in probe))
