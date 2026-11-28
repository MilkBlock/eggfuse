import json
import tempfile
import unittest
from pathlib import Path

from cell_training_log import TrainingLog


class TelemetryTest(unittest.TestCase):
    def test_journal_drains_and_preserves_measured_zero(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "run.jsonl"
            j = TrainingLog(p, {"seed": 71})
            j.log({"train/grad_norm_preclip": 0.0}, 64)
            j.finish()
            rows = list(map(json.loads, p.read_text().splitlines()))
            self.assertEqual(["config", "metrics", "finish"], [x["kind"] for x in rows])
            self.assertEqual(rows[1]["metrics"], {"train/grad_norm_preclip": 0.0})


class ProjectionTest(unittest.TestCase):
    def setUp(self):
        from importlib.util import find_spec
        if find_spec("swanlab") is None:
            self.skipTest("SwanLab dashboard environment required")

    def test_live_run_displays_parameter_counts_from_its_own_header(self):
        import sqlite3

        from cell_dashboard import journal_worker

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path = root / "local-s71-live.jsonl"
            journal = TrainingLog(path, {"registered": 32874, "model": "local-s71"})
            journal.log({"parameters/forward": 18880, "parameters/backward": 4160,
                         "train/tokens": 1001, "train/seconds": 7}, 1001)
            journal.finish()
            journal_worker(path, root)
            with sqlite3.connect(root / "runs.swanlab") as db:
                charts = {r[0] for r in db.execute("select name from chart")}
                self.assertTrue({"parameters/total", "parameters/forward", "parameters/backward",
                                 "train/tokens", "train/seconds"} <= charts)

    def test_resumed_journal_has_its_own_live_run_and_native_metrics(self):
        import sqlite3

        from cell_dashboard import journal_worker

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path = root / "full-s71-live.jsonl"
            for step in (10000, 20000):
                offset = path.stat().st_size if path.exists() else 0
                j = TrainingLog(path, {"registered": 32874, "model": "full-s71"})
                j.log({"train/tokens": step, "native_256/loopfact_g193_paid": 256}, step)
                j.finish()
                journal_worker(path, root, offset)
                journal_worker(path, root, offset)
            with sqlite3.connect(root / "runs.swanlab") as db:
                names = [r[0] for r in db.execute("select name from experiment order by id")]
                self.assertEqual(len(names), 2)
                self.assertIn("resume-", names[1])
                self.assertIn(("native_256/loopfact_g193_paid",), list(db.execute("select name from chart")))

    def test_root_and_higher_suffix_not_double_counted(self):
        from cell_dashboard import token_ability

        x = {
            "r": {"stats": {"neural_tokens": 2, "higher_selected": 1}},
            "requests": [
                {
                    "tid": 4,
                    "refs": [3],
                    "owner": 3,
                    "reply": [3, 0],
                    "ops": 2,
                    "complete": True,
                },
                {
                    "tid": 5,
                    "refs": [],
                    "owner": 4,
                    "reply": [4, 0],
                    "ops": 0,
                    "complete": True,
                },
                {
                    "tid": 1,
                    "refs": [7],
                    "owner": 4,
                    "reply": [5, 0],
                    "ops": 3,
                    "complete": True,
                },
            ],
        }
        c = token_ability(x, 5)
        self.assertEqual((c["Higher/generated"], c["Higher/signed_ops"]), (1, 3))
        self.assertEqual(
            (c["parents_0/complete_with_work"], c["Primitive/signed_ops"]), (1, 2)
        )

    def test_shortfall_and_continuation_use_separate_steps(self):
        from cell_dashboard import provenance_rows

        rows = provenance_rows(
            [
                {
                    "mode": "total",
                    "budget": 16,
                    "paid": 13,
                    "shortfall": 3,
                    "statuses": {"duplicates": 2},
                },
                {
                    "mode": "continuation",
                    "budget": 16,
                    "paid": 12,
                    "shortfall": 4,
                    "continuation_ept": 0.25,
                    "statuses": {"rejected": {"binding": 2}},
                },
            ],
            None,
        )
        self.assertEqual(rows[0][0], 16)
        self.assertEqual(rows[0][1]["total/shortfall"], 3)
        self.assertEqual(rows[0][1]["continuation/run_rejected_binding"], 2)
        self.assertNotIn("total/eps", rows[0][1])

    def test_offline_backend_roundtrip_and_idempotence(self):
        import sqlite3

        from cell_dashboard import Sink

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            sink = Sink(root)
            for _ in range(2):
                sink.publish(
                    "test fit",
                    "source-checksum",
                    {"source": "fixture"},
                    [(10, {"train/ce": 1.25})],
                )
            db = sqlite3.connect(root / "runs.swanlab")
            self.assertEqual(
                db.execute("select count(*) from experiment").fetchone()[0], 1
            )
            self.assertEqual(
                sink.db.execute("select count(*) from committed").fetchone()[0], 1
            )
            self.assertTrue(list(root.glob("run-*/logs/*/*")))
            db.close()
            sink.db.close()
