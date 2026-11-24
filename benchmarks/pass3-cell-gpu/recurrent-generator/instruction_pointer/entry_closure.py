"""Compile continuations from the typed entry and named results of earlier stages.
Offline exact witnesses cost and select statically compiled proposals.
"""

import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
from itertools import product
import json
from math import prod
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from int_parameters import StructuralBake, link_layouts
from receipt_bake import Snapshot, read, save
from receipt_takeover import replay
from ripsat_layout import signatures
from train_ripsat import layout_id


def named(arg):
    a = arg["address"]
    return a["token"], a["op"], arg["version"]


class Rules:
    def __init__(self, contract):
        self.rules = contract["rules"]
        self.inputs = [tuple(a["table"] for a in r["inputs"]) for r in self.rules]
        self.subs = defaultdict(set)
        for r, tabs in enumerate(self.inputs):
            for t in tabs:
                self.subs[t].add(r)

    def root(self, rid):
        return ((rid, 0, tuple((-1, i) for i in range(len(self.inputs[rid])))),)

    def extensions(self, unit, counts, ambiguity=16):
        ports = defaultdict(list)
        for i, tab in enumerate(self.inputs[unit[0][0]]):
            ports[tab].append((-1, i))
        latest = set()
        for i, (r, _, _) in enumerate(unit):
            for pc, site in self.rules[r]["outputs"].items():
                ports[site["table"]].append((i, int(pc)))
                if i + 1 == len(unit):
                    latest.add(site["table"])
        for r in sorted(set().union(*(self.subs[t] for t in latest))):
            options = [ports[t] for t in self.inputs[r]]
            size = prod(map(len, options))
            if size == 0:
                counts["needs_additional_external_table"] += 1
                continue
            if size > ambiguity:
                counts["compile_ambiguity_budget"] += 1
                continue
            for wires in product(*options):
                if any(i == len(unit) - 1 for i, _ in wires):
                    yield (r, len(unit), wires)


class Tape:
    def __init__(self, folder, binary):
        self.folder = folder
        self.program = read(folder / "program.json")
        contract = json.loads(
            subprocess.check_output(
                [binary, "receipt-contract", folder / "program.json"]
            )
        )
        if contract["recipe_sha256"] != self.program["recipe"]["sha256"]:
            raise ValueError("wrong native contract")
        self.rules = Rules(contract)
        saved = read(folder / "tape.json")
        self.tape = saved["requests"]
        repairs = {ev["token"]: ev for ev in saved["repair_events"]}
        self.q = {q["token"]: q for q in self.tape}
        self.schedule = defaultdict(list)
        for f in map(json.loads, (folder / "memory.jsonl").open()):
            for r, _ in f["rules"]:
                self.schedule[r].append(f["run"])
        self.snap = Snapshot(folder)
        self.index = {}
        self.by_rule = defaultdict(list)
        for q in self.tape:
            args = tuple(map(named, q["parents"]))
            for tab, (token, op, version) in zip(
                self.rules.inputs[q["rule"]], args, strict=True
            ):
                if self.snap.version(token, op, q["run"]) != version:
                    raise ValueError(
                        "training entry references unpublished or stale evidence"
                    )
                if token in repairs:
                    ev = repairs[token]
                    if (
                        op not in ev["operations"]
                        or ev["visible_from_run"] > q["run"]
                        or contract["repair_outputs"][str(ev["merge_table"])][str(op)]
                        != tab
                    ):
                        raise ValueError("repair result is not an entry witness")
            self.index[q["run"], q["rule"], args] = q["token"]
            self.by_rule[q["rule"]].append((q["token"],))

    def extend(self, tokens, step):
        rule, _, wires = step
        prev = self.q[tokens[-1]]["run"]
        times = self.schedule[rule]
        i = bisect_right(times, prev)
        if i == len(times):
            return
        args = []
        for owner, pc in wires:
            if owner < 0:
                a = named(self.q[tokens[0]]["parents"][pc])
            else:
                t = tokens[owner]
                v = self.snap.version(t, pc, self.q[t]["run"] + 1)
                if v is None:
                    return
                a = (t, pc, v)
            args.append(a)
        t = self.index.get((times[i], rule, tuple(args)))
        if t is not None:
            return (*tokens, t)

    def occasions(self, unit):
        cases = self.by_rule[unit[0][0]]
        for step in unit[1:]:
            cases = [b for ts in cases if (b := self.extend(ts, step))]
        return cases


def savings(unit):
    return sum(len(w) for _, _, w in unit[1:])


def compile_catalog(t, limit=48, depth=8):
    counts = Counter()
    options = {}
    front = {t.rules.root(r): ts for r, ts in t.by_rule.items()}
    for level in range(1, depth):
        found = {}
        for unit, roots in front.items():
            for step in t.rules.extensions(unit, counts):
                counts["typed_wirings"] += 1
                instances = [b for ts in roots if (b := t.extend(ts, step))]
                if instances:
                    found[(*unit, step)] = instances
        rank = lambda u: (-savings(u) * len(found[u]), -len(found[u]), u)
        front = {u: found[u] for u in sorted(found, key=rank)[:limit]}
        options.update(front)
        if not front:
            break
    # Marginal utility over distinct actual child commits; overlapping layouts
    # do not independently earn the same observed handoff.
    remaining = {
        u: {tok: len(u[i][2]) for ts in occ for i, tok in enumerate(ts) if i}
        for u, occ in options.items()
    }
    selected = []
    covered = set()
    while remaining and len(selected) < limit:
        best = max(
            remaining,
            key=lambda u: sum(v for t, v in remaining[u].items() if t not in covered),
        )
        if not (remaining[best].keys() - covered):
            break
        covered.update(remaining.pop(best))
        selected.append(best)
    return selected, counts, options


def build(root, binary, out):
    out.mkdir(exist_ok=True, parents=True)
    t = Tape(root / "sum", binary)
    units, counts, options = compile_catalog(t)
    manifest = dict(
        signatures=signatures(t.program),
        layouts=units,
        **StructuralBake(t.program).manifest(units),
    )
    train_checks = {}
    admitted = []
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "layout.json"
        ref = read(t.folder / "capture.json")
        for u in units:
            save(path, [u])
            try:
                test = replay(
                    t.folder,
                    binary,
                    path,
                    dict(internal_tokens=options[u][0]),
                    t.tape,
                    ref,
                )
            except ValueError as e:
                train_checks[layout_id(u)] = dict(rejected=str(e))
                continue
            admitted.append(u)
            train_checks[layout_id(u)] = test
    manifest = dict(
        signatures=manifest["signatures"],
        layouts=admitted,
        **StructuralBake(t.program).manifest(admitted),
    )
    save(out / "catalog.json", manifest)
    save(
        out / "construction.json",
        dict(
            counts=counts,
            candidates_with_support=len(options),
            selected=len(units),
            admitted=len(admitted),
            native=train_checks,
        ),
    )
    for name in ("sum", "dot", "fact", "loopfact", "sum-divisors"):
        src = t if name == "sum" else Tape(root / name, binary)
        rows = {}
        for uid, unit in link_layouts(src.program, manifest):
            cases = src.occasions(unit)
            if cases:
                rows[uid] = cases
        save(out / (name + "-occasions.json"), rows)
        print(name, len(rows), sum(map(len, rows.values())), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for k in ("root", "binary", "out"):
        p.add_argument(k, type=Path)
    a = p.parse_args()
    build(a.root, a.binary, a.out)
