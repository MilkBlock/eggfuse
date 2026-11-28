"""Small native programs with two same-interface, conditionally productive Higher bodies."""

import json
import subprocess
from time import perf_counter
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from completion_context import read


def program(depth, jobs, seed, fork=False, flip=False, common=False):
    rng = np.random.default_rng(seed)
    names = ["Seed", "Noise", "Permit", "Mid", "DoneL", "DoneR"] + [
        f"{s}{j}" for j in range(depth) for s in "LR"
    ]
    lines = [
        f"(relation {name} ({'i64' if name == 'Permit' else 'i64 i64'}))"
        for name in names
    ]
    lines += ["(ruleset root)", "(rule ((Seed x y)) ((Mid x y)) :ruleset root)"]
    for j in range(depth):
        lines.append(f"(ruleset step{j})")
        branch = list("LR")
        rng.shuffle(branch)
        for s in branch:
            source = "Mid" if j == 0 else f"{s}{j - 1}"
            guard = (" (= x y)" if s == "L" else " (!= x y)") if j == 0 else ""
            op = "+" if s == "L" else "-"
            join = " (Mid x u)" if fork and j == depth - 1 and j > 0 else ""
            operand = "(max y u)" if join else "y"
            lines.append(
                f"(rule (({source} x y){guard}{join}) (({s}{j} x ({op} {operand} {j + 1}))) :ruleset step{j})"
            )
    lines.append("(ruleset finish)")
    for s in "LR":
        lines.append(
            f"(rule (({s}{depth - 1} x y) (Permit x)) ((Done{s} x y)) :ruleset finish)"
        )
    if common:
        # Both branch bodies now publish the identical terminal relation and op.
        lines = [line for line in lines if ":ruleset finish)" not in line]
        lines.extend(["(relation Common (i64 i64))", "(ruleset export)"])
        for side in "LR":
            lines.append(
                f"(rule (({side}{depth - 1} x y)) ((Common x y)) :ruleset export)"
            )
        lines.append("(rule ((Common x y) (Permit x)) ((DoneL x y)) :ruleset finish)")
    inputs = []
    for i in range(jobs):
        x, y = rng.choice(2**27, 2, replace=False).tolist()
        if ((i + seed) % 2 == 0) != flip:
            y = x
        inputs.extend([f"(Seed {x} {y})", f"(Noise {y} {x})", f"(Permit {x})"])
    rng.shuffle(inputs)
    return (
        "\n".join(
            lines
            + inputs
            + [
                "(run-schedule (run root) "
                + " ".join(f"(run step{j})" for j in range(depth))
                + (" (run export)" if common else "")
                + " (run finish) (run finish))"
            ]
        )
        + "\n"
    )


def make(a, name, depth, jobs, seed, fork=False, flip=False, common=False):
    return compile_world(a, name, program(depth, jobs, seed, fork, flip, common))


def compile_world(a, name, source):
    d = a.out / "worlds" / name
    d.mkdir(exist_ok=True, parents=True)
    egg = d / "world.egg"
    if (d / "capture.json").exists() and egg.read_text() != source:
        raise ValueError(f"cached native source mismatch in {d}")
    if not (d / "capture.json").exists():
        egg.write_text(source)
        times = {}
        start = perf_counter()
        with TemporaryDirectory(dir=getattr(a, "compile_scratch", d)) as tmp:
            compiled = Path(tmp) / "compiled"
            subprocess.run(
                [a.compiler, "compile", "--source", egg, "--output", compiled,
                 *(["--bake-source", a.frozen_bake_source] if hasattr(a, "frozen_bake_source") else [])],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            (d / "program.json").write_bytes((compiled / "program.json").read_bytes())
        times["compile_s"] = perf_counter() - start
        ir = d / "program.json"
        for fn, cmd in [
            ("contract", ["receipt-contract", ir]),
            (
                "capture",
                [
                    "capture",
                    ir,
                    d / "teacher.json",
                    "audit",
                    "--export",
                    d / "reference.json",
                    "--ept",
                ],
            ),
        ]:
            start = perf_counter()
            data = subprocess.check_output([a.runtime_binary, *cmd])
            times[fn + "_s"] = perf_counter() - start
            (d / f"{fn}.json").write_bytes(data)
        (d / "preparation.json").write_text(json.dumps(times))
    return d


class World:
    def __init__(self, d, actor, sides="LR", *, entry_table="Mid"):
        self.dir = d
        self.prog = read(d / "program.json")
        self.contract = read(d / "contract.json")
        self.cat = actor.catalog_type(self.prog, integer_parameters=True)
        self.tabs = [x["name"] for x in self.prog["recipe"]["tables"]]
        self.outputs = []
        self.roles = []
        self.layouts = []
        self.outnames = {}
        for rid, r in enumerate(self.contract["rules"]):
            outs = {self.tabs[v["table"]]: int(pc) for pc, v in r["outputs"].items()}
            self.outputs.append(outs)
            for name in outs:
                self.outnames[name] = rid
            self.roles.append([x["table"] for x in r["inputs"]])
            self.layouts.append([(rid, 0, [(-1, j) for j in range(len(r["inputs"]))])])
        self.primitives = len(self.layouts)
        self.root = self.outnames[entry_table] if entry_table is not None else 0
        self.export_pc = {}
        for side in sides:
            body = list(self.layouts[self.root])
            src = entry_table
            while (dest := f"{side}{len(body) - 1}") in self.outnames:
                rid = self.outnames[dest]
                producers = {
                    tab: (j, pc)
                    for j, (pred, _, _) in enumerate(body)
                    for tab, pc in self.outputs[pred].items()
                }
                wires = [producers[self.tabs[t]] for t in self.roles[rid]]
                body.append((rid, len(body), wires))
                src = dest
            if "Common" in self.outnames:
                (rid,) = [
                    i
                    for i, outputs in enumerate(self.outputs)
                    if "Common" in outputs and self.roles[i] == [self.tabs.index(src)]
                ]
                body.append(
                    (rid, len(body), [(len(body) - 1, self.outputs[body[-1][0]][src])])
                )
                src = "Common"
            self.export_pc[len(self.layouts)] = self.outputs[body[-1][0]][src]
            self.layouts.append(body)
        self.finals = {
            self.outnames[n] for n in ("DoneL", "DoneR") if n in self.outnames
        }

    def menu(self, rules):
        return [i for i, body in enumerate(self.layouts) if body[0][0] in rules]
