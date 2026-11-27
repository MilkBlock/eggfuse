import json
import os
import subprocess
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from completion_context import environment
from completion_fit import schedule


class Curriculum(unittest.TestCase):
    def test_minibatch_identity_and_retention(self):
        for seed in (9633, 5003, 1777):
            expected = Counter((n, j) for n in range(8) for j in range(96))
            for arm in "ABC":
                stages = schedule(arm, 96, seed)
                self.assertEqual(
                    expected, Counter(x for stage in stages for x in stage)
                )
                maxima = [max(n for n, j in stage) for stage in stages]
                if arm in "BC":
                    self.assertEqual(maxima, list(range(8)))
                if arm == "C":
                    self.assertIn(0, [n for n, j in stages[-1]])
                if arm == "A":
                    self.assertEqual(len({n for n, j in stages[0]}), 8)

    def test_shuffles_keep_input_and_guard(self):
        source, rows = environment(16, "pair", 80, 0)
        other, permuted = environment(16, "pair", 80, 1)
        self.assertNotEqual(source, other)
        self.assertEqual(Counter(rows), Counter(permuted))
        joined = [(x, z) for _, x, y in rows for _, b, z in rows if y == b]
        self.assertEqual((len(joined), sum(x < z for x, z in joined)), (2, 1))
        for name, n in [("pair", 2), ("triple", 3), ("unary", 1)]:
            src, _ = environment(16, name, 80, 1)
            self.assertEqual(
                next(
                    line for line in src.splitlines() if ":ruleset probe" in line
                ).count("(Edge "),
                n,
            )


@unittest.skipUnless(
    os.getenv("CELL_REPLAY") and os.getenv("CELL_COMPILER"),
    "requires named native replay and compiler",
)
class NativeNames(unittest.TestCase):
    def test_permutation_preserves_effects_and_rejects_wrong_namespace(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            src = d / "world.egg"
            src.write_text(environment(4, "pair", 80, 0)[0])
            subprocess.run(
                [
                    os.environ["CELL_COMPILER"],
                    "compile",
                    "--source",
                    src,
                    "--output",
                    d / "ir",
                ],
                capture_output=True,
                check=True,
            )

            def cmd(role, tape, *args, check=True):
                return subprocess.run(
                    [
                        os.environ["CELL_REPLAY"],
                        role,
                        d / "ir/program.json",
                        tape,
                        "audit",
                        *map(str, args),
                    ],
                    capture_output=True,
                    check=check,
                )

            named = []
            graphs = set()
            for seed in (94391, 67203250, None):
                tape = d / f"{seed}.json"
                extra = ("--address-seed", seed) if seed is not None else ()
                cmd("capture", tape, "--ept-origins", *extra)
                saved = json.loads(tape.read_bytes())
                self.assertEqual(saved.get("address_seed"), seed)
                (request,) = saved["requests"]
                named.append(request["parents"])
                rep = json.loads(cmd("replay", tape, 2, "--ept-origins").stdout)
                graphs.add(rep["state_sha"])
                self.assertEqual(rep["counts"]["accepted"], 1)
                self.assertEqual(dict(rep["ept"]["origins"])[request["token"]], 1)
            self.assertNotEqual(named[0], named[1])
            self.assertEqual(len(graphs), 1)
            fail = cmd(
                "replay",
                d / "94391.json",
                2,
                "--recall",
                d / "67203250.json",
                check=False,
            )
            self.assertNotEqual(fail.returncode, 0)
            self.assertIn(b"mismatch", fail.stderr)


if __name__ == "__main__":
    unittest.main()
