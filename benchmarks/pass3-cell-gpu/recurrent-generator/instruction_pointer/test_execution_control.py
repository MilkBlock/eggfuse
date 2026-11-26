import os
import unittest
from pathlib import Path
from types import SimpleNamespace

from execution_control import CONTINUE, SEAL, SUBMIT, window
from execution_control_data import supervision
from latent_cell_flow import ZERO


class WindowTests(unittest.TestCase):
    def run_window(self, mode, picks, allowance=2):
        decisions = iter(picks)
        memory = SimpleNamespace(context=lambda: ZERO, event=ZERO)
        submitted = []

        def send(draft):
            self.assertTrue(draft)
            submitted.append(list(draft))
            return [(len(submitted), 0)] * len(draft)

        log, balance, reason = window(
            memory,
            allowance,
            mode,
            lambda x, mask: next(decisions),
            lambda: [42],
            send,
            float("inf"),
        )
        return log, submitted, balance, reason

    def test_two_submits_same_window(self):
        log, submitted, balance, reason = self.run_window("B", [CONTINUE, SUBMIT] * 2)
        self.assertEqual(submitted, [[42], [42]])
        self.assertEqual([a["sent"] for a in log], [0, 0, 1, 1])
        self.assertEqual((balance, reason), (0, "budget_truncation"))

    def test_batch_or_neural_exit(self):
        self.assertEqual(
            self.run_window("B", [CONTINUE, CONTINUE, SUBMIT])[1], [[42, 42]]
        )
        self.assertEqual(self.run_window("C", [SEAL])[1:], ([], 2, "neural_seal"))
        with self.assertRaises(ValueError):
            self.run_window("B", [SEAL])
        with self.assertRaises(ValueError):
            self.run_window("C", [SUBMIT])

    def test_unknown_and_role_of_omission(self):
        row = {"action": SEAL, "mask": [True, False, True], "x": [1]}

        def labels(credit):
            return list(supervision([{"actions": [row], "exit": {"credited": credit}}]))

        self.assertEqual(labels(None), [])
        self.assertEqual(labels([]), [])
        self.assertEqual(labels([[574, 1]])[0][2:], (CONTINUE, True))

    @unittest.skipUnless(
        os.environ.get("EXECUTION_CONTROL_OUTPUT"), "native replay artifacts"
    )
    def test_live_575_and_late_574(self):
        import json

        root = Path(os.environ["EXECUTION_CONTROL_OUTPUT"])
        r = json.loads((root / "report/regressions.json").read_bytes())
        self.assertEqual(r["574_late"]["rejection"], {"untriggered_rule": 1})
        self.assertEqual(r["575_continue"]["delta"], 1)
        rows = r["575_live"][2]["submits"]
        self.assertEqual([s[2] for s in rows], ["binding", "accepted"])
        self.assertEqual(rows[0][3], rows[1][3])
        self.assertNotEqual(rows[0][1], rows[1][1])


if __name__ == "__main__":
    unittest.main()
