import unittest

from control_credit_experience import records
from dual_credit import compare, marginal
from execution_control import CONTINUE, SEAL


class DualCreditTests(unittest.TestCase):
    def test_origin_reassignment_is_unknown(self):
        prefix, extra = [{"token": 1}], [{"token": 2}]
        base = {"origins": {1: 2}, "ops": 2}
        self.assertIsNone(
            marginal(base, {"origins": {1: 1, 2: 2}, "ops": 3}, prefix, extra)
        )
        self.assertIsNone(
            marginal(base, {"origins": {1: 2, 2: 2}, "ops": 3}, prefix, extra)
        )
        self.assertEqual(marginal(base, base, prefix, extra), [0])

    def test_unmatched_policy_branches(self):
        obs = {"prefix": "p", "pages": [1], "facts": [5], "ops": 4, "wall": 1}
        with self.assertRaises(ValueError):
            compare({"continue": obs, "seal": dict(obs, prefix="q")})
        with self.assertRaises(ValueError):
            compare({"continue": obs, "seal": dict(obs, pages=[])})
        self.assertEqual(
            compare({"continue": obs, "seal": dict(obs, facts=[7])})["lost"], [7]
        )

    def test_policy_failure_preserves_teacher_witness(self):
        a = {
            "action": SEAL,
            "state": "s",
            "mask": [True, False, True],
            "x": [0],
            "credit": {
                "timing": ["control", CONTINUE, "teacher"],
                "omission": ["exit", 2, "teacher"],
                "cost": ["control", {}, "observed"],
            },
        }
        sh = {
            "cohort": "neural",
            "signature": "recipe",
            "program": "p",
            "pairs": [],
            "windows": [
                {
                    "stage": 1,
                    "epoch": 2,
                    "run": 3,
                    "control_events": [a],
                    "cell_credit": [],
                    "publication_probe_ids": [],
                }
            ],
        }
        twins = [
            dict(
                state="s",
                stage=1,
                epoch=2,
                run=3,
                program="p",
                checkpoint="frozen",
                slots_per_page=16,
                teacher_potential={"witnesses": [["A", 2]]},
                policy_realization={
                    k: {"first_page_ops": 0} for k in ["continue", "seal"]
                },
                control_effect={"gained": [], "lost": []},
            )
        ]
        (r,) = records(sh, {"records": []}, dual=twins)
        self.assertTrue(r["masks"]["teacher_witness"])
        self.assertTrue(r["masks"]["realized_continue"])
        self.assertFalse(r["masks"]["realized_allocation"])
        self.assertEqual(set(r["credit"]), {"cost"})
        self.assertEqual(r["x"], [0])
        (r,) = records(sh, {"records": []})
        self.assertIsNone(r["policy_realization"])
        self.assertFalse(any(r["masks"].values()))
