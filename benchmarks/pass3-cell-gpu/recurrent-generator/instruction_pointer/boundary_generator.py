"""Re-run the frozen generator with read-only route/issue instrumentation; audit topology/trace menus offline."""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import torch

from boundary_inputs import BASE, CASE, frozen_tape, native
from discrete_cells import Memory, load_enc
from discrete_study import load
from entry_closure import Tape
from recursive_train import binary, folder, read
from region_bake import linked
from region_owner import Ownership
from scaling_bake import save
from scaling_native import menus
from transaction_native import execute


@torch.no_grad()
def audit(root, out, actor):
    d = folder(root, CASE)
    t = Tape(d, binary(root))
    enc, scorer = load_enc(t.program, actor)
    ct = native(binary(root), "receipt-contract", d / "program.json")
    trace = linked(t.program, read(BASE / "menu.json"))
    top = menus(
        ct,
        enc,
        d,
        "wide",
        set(read(Path("run-recall/parameterized-deep-ripsat/catalog.json"))["structural_keys"]),
        256,
    )
    targets = {p["address"]["token"] for ts in t.occasions(trace[56]) for p in t.q[ts[0]]["parents"]}
    covers = {}
    for name, menu in [("trace", trace), ("wide", top)]:
        found = []
        for r, unit in menu.items():
            steps = [j for j, (rid, _, _) in enumerate(unit) if rid in (49, 50, 51)]
            if not steps:
                continue
            occ = t.by_rule[r]
            for j, step in enumerate(unit):
                if j:
                    occ = [z for ts in occ if (z := t.extend(ts, step))]
                if j in steps:
                    found.append(
                        dict(
                            root=r,
                            step=j,
                            rule=step[0],
                            size=len(unit),
                            prefix_occurrences=len(occ),
                            target_producer_instances=sorted({ts[-1] for ts in occ} & targets),
                        )
                    )
        covers[name] = found
    save(out / "catalog.json", covers)
    marks, nets = load(SimpleNamespace(out=Path("run-recall/discrete-computation-flow")))
    m = Memory(enc, ct, trace, scorer)
    m.audit_routes = True
    stages = defaultdict(Counter)
    rules = {49, 50, 51, 56, 279, 346, 574, 575}

    class Probe(Ownership):
        def run_snapshot(self, frame, pub, rd, model, txn, stats, deadline):
            self.current = frame["run"]
            super().run_snapshot(frame, pub, rd, model, txn, stats, deadline)

        def send(self, items, txn, stats):
            rows = super().send(items, txn, stats)
            if len(items) <= txn.capacity:
                for item, row in zip(items, rows, strict=True):
                    c = item.cell
                    if c.higher or c.rule in rules:
                        stages[self.current][f"issued/{c.rule}/{int(c.higher)}/{int(row[1])}"] += 1
            return rows

    pol = Probe(m, marks, nets, "empty", 4, 536, 32)

    def selected(k):
        if k[1] or k[0] in rules:
            stages[pol.current][f"routed/{k[0]}/{int(k[1])}"] += 1

    m.on_template_draw = selected
    original = marks.draw

    def draw(*args, **kwargs):
        c = original(*args, **kwargs)
        if c and (c.higher or c.rule in rules):
            stages[pol.current][f"addressed/{c.rule}/{int(c.higher)}"] += 1
        return c

    marks.draw = draw
    with TemporaryDirectory(dir=out) as tmp:
        result = execute(root, CASE, study=pol, series=tmp, seconds=240)
        baseline = next(
            q
            for line in (BASE / "runs.jsonl").open()
            if (q := json.loads(line))["case"] == CASE and q["label"] == "routes32" and q["mode"] == "E"
        )
        old = frozen_tape()["tape"]
        issued = read(Path(tmp) / (CASE + "-stream-multi") / "issued.json")
        if old != issued or any(
            result[k] != baseline[k] for k in ("state_sha", "paid", "verdicts", "signed_ops")
        ):
            raise ValueError("read-only instrumentation changed the rollout")
    save(
        out / "generator.json",
        dict(stages=stages, state_sha=result["state_sha"], paid=result["paid"], tape_identical=True),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for k in ("root", "out", "actor"):
        p.add_argument(k, type=Path)
    a = p.parse_args()
    torch.set_num_threads(1)
    audit(a.root, a.out, a.actor)
