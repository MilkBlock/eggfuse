"""Held external writer and competing scheduled rule; static wiring from the compiled Recipe."""

import json
import subprocess

from entry_closure import Tape
from receipt_takeover import replay_many
from recursive_train import binary, folder, read
from scaling_bake import save

OPEN = "response-held-permit"


def build(a):
    d = folder(a.data, OPEN)
    src = d.with_suffix(".egg")
    text = """
(relation Ticket(i64))
(relation Supply(i64))
(relation Permit(i64))
(relation Other(i64))
(relation Root(i64))
(relation Left(i64))
(relation Right(i64))
(relation Sink(i64))
(ruleset root)(ruleset write)(ruleset left)(ruleset right)(ruleset sink)
(rule ((Ticket x) (Permit x)) ((Root x)) :ruleset root)
(rule ((Supply x)) ((Permit x)) :ruleset write)
(rule ((Supply x)) ((Other x)) :ruleset write)
(rule ((Root x)) ((Left x)) :ruleset left)
(rule ((Root x)) ((Right x)) :ruleset right)
(rule ((Left x) (Right x)) ((Sink x)) :ruleset sink)
(Ticket 29)(Ticket 31)(Supply 29)
(run-schedule (run root) (run write) (run root) (run left) (run right) (run sink) (run sink))
"""
    if d.exists() and src.read_text() != text:
        raise ValueError("existing held program differs")
    src.write_text(text)
    if not (d / "program.json").exists():
        subprocess.run(
            [a.compiler, "compile", "--source", src, "--output", d],
            check=True,
            stdout=subprocess.DEVNULL,
        )
    exe = binary(a.data)
    cap = json.loads(
        subprocess.check_output(
            [
                exe,
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
    t = Tape(d, exe)
    # The rule IDs refer to this compiled program. Validate every wire against its input table.
    ids = {
        r["effects"][0]["call"]["table"]: i
        for i, r in enumerate(read(d / "program.json")["recipe"]["rules"])
    }
    unit = [
        (ids["Root"], 0, [(-1, 0), (-1, 1)]),
        (ids["Left"], 1, [(0, 0)]),
        (ids["Right"], 2, [(0, 0)]),
        (ids["Sink"], 3, [(1, 0), (2, 0)]),
    ]
    save(d / "fixture-roles.json", ids)
    for rid, _, wires in unit:
        assert len(wires) == len(t.rules.inputs[rid])
        for j, (s, p) in enumerate(wires):
            if s >= 0:
                assert (
                    t.rules.rules[unit[s][0]]["outputs"][str(p)]["table"]
                    == t.rules.inputs[rid][j]
                )
    save(d / "layouts.json", [unit])
    hits = t.occasions(unit)
    assert len(hits) == 1
    proof = replay_many(d, exe, d / "layouts.json", [(0, hits[0])], t.tape, cap)
    return d, unit, proof
