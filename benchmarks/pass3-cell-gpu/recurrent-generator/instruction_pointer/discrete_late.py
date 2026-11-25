"""A held program with an initially missing entry that can only be produced by a later paid rule."""

import argparse
import json
import subprocess
from pathlib import Path

import torch

from discrete_rollout import run
from discrete_study import save
from entry_closure import Tape
from receipt_takeover import replay_many
from recursive_train import binary

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for k in ("root", "out", "actor", "compiler"):
        p.add_argument(k, type=Path)
    a = p.parse_args()
    torch.set_num_threads(1)
    a.case = "edit-held-late-entry"
    d = a.root / "recursive-agent" / a.case
    src = d.with_suffix(".egg")
    src.write_text("""
(relation Ticket(i64))(relation Seed(i64))(relation Left(i64))(relation Last(i64))
(ruleset a)(ruleset b)(ruleset publish)
(rule ((Seed x)) ((Left x)) :ruleset a)
(rule ((Left x)) ((Last x)) :ruleset b)
(rule ((Ticket x)) ((Seed x)) :ruleset publish)
(Ticket 51)
(run-schedule (run a) (run b) (run publish) (run a) (run b) (run b))
""")
    if not (d / "program.json").exists():
        subprocess.run(
            [a.compiler, "compile", "--source", src, "--output", d], stdout=subprocess.DEVNULL, check=True
        )
    cap = json.loads(
        subprocess.check_output(
            [
                binary(a.root),
                "capture",
                d / "program.json",
                d / "tape.json",
                "audit",
                "--memory",
                d / "memory.jsonl",
                "--ept",
            ]
        )
    )
    save(d / "capture.json", cap)
    t = Tape(d, binary(a.root))
    # The recipe compiler assigns rule IDs from the declaration order; verify both wire types.
    assert t.rules.rules[0]["outputs"]["0"]["table"] == t.rules.inputs[1][0]
    unit = [(0, 0, [(-1, 0)]), (1, 1, [(0, 0)])]
    save(d / "layouts.json", [unit])
    hit = t.occasions(unit)
    assert len(hit) == 1
    cert = replay_many(d, binary(a.root), d / "layouts.json", [(0, hit[0])], t.tape, cap)
    save(a.out / "late-entry-certificate.json", cert)
    for a.block in range(2):
        a.seed = 536
        a.waves = 2
        a.seconds = 60
        arms = ["editor:1", "flow:4", "empty:4", "supervised-empty:1"]
        a.arms = arms if a.block == 0 else arms[::-1]
        run(a)
