"""Scripted integration challenge for two overlapping instances, a guard failure and an unrelated job.
This drives the real CCP process. Policy decisions here are fixed test vectors, not neural scores.
"""

import argparse
import json
import subprocess
from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory

import torch

from discrete_cells import Memory, load_enc
from discrete_draft import Cell, Item
from recursive_train import binary, folder, read
from region_owner import Ownership
from scaling_bake import save
from transaction_native import execute

SOURCE = """
(relation Seed (i64))
(relation Left (i64))
(relation Right (i64))
(relation Attempt (i64))
(relation Shared (i64))
(relation Lost (i64))
(relation Other (i64))
(relation X (i64))
(relation Y (i64))
(ruleset root)
(ruleset shared)
(ruleset finish)
(rule ((Seed x)) ((Left (+ x 1))) :ruleset root)
(rule ((Seed x)) ((Right (+ x 2))) :ruleset root)
(rule ((Seed x)) ((Attempt x)) :ruleset root)
(rule ((Seed x)) ((Shared (+ x 3))) :ruleset shared)
(rule ((Seed x) (< x 0)) ((Lost x)) :ruleset shared)
(rule ((Seed x)) ((Other x)) :ruleset shared)
(rule ((Left a) (Shared b)) ((X (+ a b))) :ruleset finish)
(rule ((Right a) (Shared b)) ((Y (+ a b))) :ruleset finish)
(Seed 5)
(run-schedule (run root) (run shared) (run finish) (run finish))
"""


def challenge(root, out, compiler, actor):
    case = "region-overlap-fixture"
    d = folder(root, case)
    d.mkdir(exist_ok=True, parents=True)
    egg = d.with_suffix(".egg")
    egg.write_text(SOURCE)
    with TemporaryDirectory(dir=out) as tmp:
        build = Path(tmp) / "bake"
        subprocess.run(
            [compiler, "compile", "--source", egg, "--output", build], check=True, stdout=subprocess.DEVNULL
        )
        copyfile(build / "program.json", d / "program.json")
        exe = binary(root)
        cap = subprocess.check_output([exe, "capture", d / "program.json", d / "tape.json", "audit", "--ept"])
        (d / "capture.json").write_bytes(cap)
        contract = json.loads(subprocess.check_output([exe, "receipt-contract", d / "program.json"]))
        prog = read(d / "program.json")
        names = [t["name"] for t in prog["recipe"]["tables"]]
        spec = {}
        for r, rule in enumerate(contract["rules"]):
            for pc, site in rule["outputs"].items():
                spec[names[site["table"]]] = r, int(pc)
        menu = {}
        for side, target in (("Left", "X"), ("Right", "Y")):
            r, pc = spec[side]
            shared, p = spec["Shared"]
            dest = spec[target][0]
            ports = {side: (0, pc), "Shared": (1, p)}
            wires = [ports[names[i["table"]]] for i in contract["rules"][dest]["inputs"]]
            menu[r] = [(r, 0, [(-1, 0)]), (shared, 1, [(-1, 0)]), (dest, 2, wires)]
        r = spec["Attempt"][0]
        menu[r] = [(r, 0, [(-1, 0)]), (spec["Lost"][0], 1, [(-1, 0)])]
        enc, scorer = load_enc(prog, actor)
        memory = Memory(enc, contract, menu, scorer)

        class Script(Ownership):
            def resume_programs(self, frame, pub, txn, stats):
                super().resume_programs(frame, pub, txn, stats)
                rules = dict(frame["rules"])
                if spec["Left"][0] in rules:
                    assert len(self.confirmed.live) == 1
                    a, row = next(iter(self.confirmed.live.items()))
                    self.seed = (*a, row[0]["version"])
                    self.send(
                        [
                            Item(i, Cell(spec[side][0], (self.seed,), True))
                            for i, side in enumerate(("Left", "Right", "Attempt"))
                        ],
                        txn,
                        stats,
                    )
                if spec["Shared"][0] in rules:
                    # An ordinary proposal for a previously owned suffix, a real
                    # native rejection and an independent valid primitive all coexist.
                    results = self.send(
                        [
                            Item(i, Cell(spec[s][0], (self.seed,)))
                            for i, s in enumerate(("Shared", "Lost", "Other"))
                        ],
                        txn,
                        stats,
                    )
                    assert [int(row[1]) == 0 for row in results] == [True, False, True]

        pol = Script(memory, None, None, "noop", 1, 1, 1)
        result = execute(root, case, study=pol, series=tmp, seconds=30)
        result.pop("trace")
        assert result["exact_endpoint"] and result["work"]["higher_completed"] == 2
        assert (
            result["work"]["higher_overlap_reuses"] == 1
            and result["work"]["neural_primitive_receipt_reuses"] == 1
        )
        assert result["work"]["peak_open"] == 3 and result["work"]["suffix_rejected"] == 1
        save(out / "overlap.json", result)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for key in ("root", "out", "compiler", "actor"):
        p.add_argument(key, type=Path)
    a = p.parse_args()
    torch.set_num_threads(1)
    with torch.no_grad():
        challenge(a.root, a.out, a.compiler, a.actor)
