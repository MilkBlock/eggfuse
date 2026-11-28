"""Predeclared fresh EggCC input programs using the incumbent optimization rules and schedule."""
import copy
import json
import os
from pathlib import Path
import subprocess

import torch

from cell_kv_world import compile_world, World
from competition_egg import egg
from foundation_egg_catalogue import install
from partner_index_worlds import args
from prefix_train import make
from recursive_coverage import Target
from region_bake import linked
from exposure_train import output, sha
from scaling_archive import directory
from scaling_fit import atomic

HELD = ("shared-polynomial", "crossed-difference")


def source(a, case):
    expressions = {
        "shared-polynomial": ("(Bop (Mul) lo hi)", "(Bop (Add) mid lo)"),
        "crossed-difference": ("(Bop (Mul) hi hi)", "(Bop (Sub) lo mid)"),
    }
    mid, result = expressions[case]
    original = (a.data / "fact/source.egg").read_text()
    head, tail = original.split("(ruleset initialization)\n", 1)
    schedule = tail[tail.index("(run-schedule (repeat 1 (run initialization)))"):]
    init = f"""(ruleset initialization)
(rule () ((let it (IntT))
          (let st (StateT))
          (let out (TupleT (TCons st (TNil))))
          (let sig (TupleT (TCons it (TCons st (TNil)))))
          (let ctx (InFunc "main"))
          (let arg (Arg sig ctx))
          (let x (Get arg 0))
          (let state (Get arg 1))
          (let lo (Bop (Sub) x (Const (Int 17) sig ctx)))
          (let hi (Bop (Add) x (Const (Int 31) sig ctx)))
          (let mid {mid})
          (let value {result})
          (let body (Single (Bop (Print) value state)))
          (let fun (Function "main" sig out body))
          (FunctionHasType "main" sig out))
          :ruleset initialization)
"""
    return head + init + schedule


def world(a, actor, case):
    if case in HELD:
        local = copy.copy(a)
        local.out = output(a)
        local.compile_scratch = None
        local.frozen_bake_source = a.data / "fact/bake-source.egg"
        d = compile_world(local, case, source(a, case))
        initial = d / "empty.json"
        if not initial.exists():
            subprocess.run([a.runtime_binary, "reference", d / "program.json", "-", "time",
                            "0", "--export", initial], check=True, stdout=subprocess.DEVNULL)
        ref = Target(json.loads((d / "program.json").read_text()),
                     json.loads((d / "reference.json").read_text()))
        pre = ref.match(json.loads(initial.read_text()))
        target = set(range(len(ref.gold))) - pre
        def align(graph):
            return ref.match(graph) - pre, target
    else:
        if case not in ("fact", "loopfact", "sum-divisors"):
            raise ValueError(case)
        d, align = egg(a, case)
    w = World(d, actor, entry_table=None, sides="")
    donor = Path(os.environ["ARTIFACT_ROOT"]) / "region-owner-1126/menu.json"
    install(w, linked(w.prog, json.loads(donor.read_text())), "multi")
    return w, align


def prepare(a):
    actor = make(a, "rel").actor
    seen = {json.loads(line)["program"] for line in
            (directory(a) / "archive.jsonl").read_text().splitlines()}
    seen.update(sha(a.data / case / "program.json") for case in ("fact", "loopfact", "sum-divisors"))
    cases = {}
    for case in HELD:
        w, align = world(a, actor, case)
        sig = sha(w.dir / "program.json")
        if sig in seen:
            raise ValueError("held program previously observed")
        seen.add(sig)
        facts, goal = align(json.loads((w.dir / "reference.json").read_text()))
        if facts != goal or not goal:
            raise ValueError("native reference self-alignment failed")
        cases[case] = dict(program=sig, source=sha(w.dir / "world.egg"), reference=len(goal),
                           primitive=w.primitives, higher=len(w.layouts)-w.primitives)
    atomic(output(a) / "split.json", dict(development=["fact", "loopfact", "sum-divisors"],
        held=cases, seed=71, address_seeds=[193,307],
        curves={"A-local":[100000,250000,500000,1000000], "A-center":[100000,250000],
                "A-layer03":[100000,250000], "B-local":[100000,250000],
                "C-local":[100000,250000],"D-local":[100000,250000,500000]}))


if __name__ == "__main__":
    torch.set_num_threads(1)
    prepare(args())
