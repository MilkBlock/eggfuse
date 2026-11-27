import unittest
import json
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from completion_context import cmd, native
import numpy as np
import torch
from binding_model import bit_lanes
from binding_worlds import source, TRAIN, UNSEEN
from actor import row_features


def normalize(links):
    n = 1 + max(r for _, _, r, _ in links)
    slots = [[3 * i + j for j in range(3)] for i in range(n)]
    for a, b, c, d in links:
        slots[c][d] = slots[a][b]
    names = {}
    return tuple(tuple(names.setdefault(v, len(names)) for v in row) for row in slots)


class Fields(unittest.TestCase):
    def test_ordered_roles_and_generalization_split(self):
        seen = set(map(normalize, TRAIN.values()))
        self.assertFalse(seen.intersection(map(normalize, UNSEEN.values())))
        self.assertEqual(len(seen), len(TRAIN))

    def test_full_width_and_column_collision(self):
        vals = np.array(
            [2**53, 2**53 + 1, 2**63 - 1, 2**63, 2**64 - 1], dtype=np.uint64
        )
        for raw in [False, True]:
            keys = bit_lanes(vals, raw)
            self.assertEqual(len(np.unique(keys, axis=0)), len(vals))
            np.testing.assert_array_equal(keys[[3, 2]], bit_lanes(vals[[3, 2]], raw))
        x = row_features([(11,), (11 ^ (1 << 43),)], 32, "cpu")
        torch.testing.assert_close(x[0], x[1], atol=0, rtol=0)

    def test_filler_disjoint_and_density(self):
        for size in [4, 64]:

            def facts(i, perm, limit):
                return [
                    x
                    for x in source(
                        i, size, "eq10", perm, edge_limit=limit
                    ).splitlines()
                    if x.startswith(("(Edge ", "(Noise "))
                ]

            a = facts(500, 0, 4)
            b = facts(500, 1, 4)
            self.assertEqual(sorted(a), sorted(b))
            self.assertEqual(len(a), size)
            self.assertEqual(sum(x.startswith("(Edge ") for x in a), 4)
            self.assertFalse(set(a) & set(facts(501, 0, 4)))


@unittest.skipUnless(
    os.getenv("CELL_REPLAY") and os.getenv("CELL_COMPILER"), "native binaries required"
)
class NativeExport(unittest.TestCase):
    def test_only_published_changes_and_only_on_opt_in(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            src = d / "test.egg"
            src.write_text(source(17, 4, "merge", 0))
            ir = d / "ir"
            cmd(
                [
                    os.environ["CELL_COMPILER"],
                    "compile",
                    "--source",
                    src,
                    "--output",
                    ir,
                ]
            )
            a = SimpleNamespace(runtime_binary=os.environ["CELL_REPLAY"])
            tape = d / "teacher.json"
            native(a, ir, "capture", tape)
            baseline = None
            for enabled in [False, True]:
                framefile = d / f"{enabled}.jsonl"
                env = os.environ.copy()
                env.pop("EGGFUSE_REPLAY_FIELD_VALUES", None)
                if enabled:
                    env["EGGFUSE_REPLAY_FIELD_VALUES"] = "1"
                result = native(
                    a, ir, "replay", tape, 2, "--memory", framefile, env=env
                )
                frames = [
                    json.loads(line) for line in framefile.read_text().splitlines()
                ]
                for f in frames:
                    if not enabled:
                        self.assertNotIn("observed_fields", f)
                    else:
                        exact = f.pop("observed_fields")

                        def identity(addr):
                            return addr["token"], addr["op"]

                        self.assertEqual(
                            sorted((identity(a), v, len(xs)) for a, v, xs in exact),
                            sorted(
                                (identity(a), p["version"], len(p["hashes"]))
                                for a, p in f["updates"]
                            ),
                        )
                if not enabled:
                    baseline = (result["state_sha"], frames)
                else:
                    self.assertEqual(baseline, (result["state_sha"], frames))


if __name__ == "__main__":
    unittest.main()
