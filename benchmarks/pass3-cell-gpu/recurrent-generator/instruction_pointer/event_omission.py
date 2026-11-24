"""Offline only: find first feasible omissions on each generator's own signed history."""

import argparse, json, subprocess
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
import numpy as np
import torch
from event_generator import EventGenerator
from recursive_train import binary, folder, read, keys
from protocol_experiment import dump
from transaction_native import execute


class Observer:
    def __init__(self, run, requests):
        self.run = run
        self.targets = requests
        self.stage = [(-1, "template_or_wake") for _ in requests]

    def align(self, mem, r, order):
        for i, q in enumerate(self.targets):
            if q["rule"] == r:
                a = keys(q)
                pos = [mem.bank(mem.roles[r][j]).positions.get(a[j], -1) for j in order]
                yield i, pos

    def mark(self, i, depth, reason):
        if depth > self.stage[i][0]:
            self.stage[i] = (depth, reason)

    def prefix(self, mem, r, order, d, paths):
        for i, pos in self.align(mem, r, order):
            if np.any(np.all(paths == pos[:d], axis=1)):
                self.mark(i, 4 * d, "issued" if d == len(order) else "retrieval")

    def window(self, mem, r, order, d, parents, post, start, n, lo, count):
        for i, pos in self.align(mem, r, order):
            for row in np.where(np.all(parents == pos[:d], axis=1))[0]:
                bank = (
                    range(int(start[row]), int(start[row] + n[row]))
                    if post is None
                    else post[start[row] : start[row] + n[row]]
                )
                if pos[d] in bank:
                    self.mark(i, 4 * d + 1, "address_selection")
                    span = bank[lo[row] : lo[row] + count[row]]
                    if pos[d] in span:
                        self.mark(i, 4 * d + 2, "parent_score")


def diagnose(root, out, c, mode, rep):
    d = folder(root, c)
    w = root / f"cell-events/{mode}/{rep}" / (c + "-stream-multi")
    tape = read(w / "issued.json")
    metrics = read(w / "metrics.json")
    cmd = [binary(root), "replay", d / "program.json", w / "issued.json", "time"]
    result = dict(case=c, mode=mode, first=None)
    with TemporaryDirectory() as tmp:
        file = Path(tmp) / "audit.json"
        for n in range(1, metrics["runs"] + 1):
            qs = json.loads(
                subprocess.check_output([*cmd, str(n - 1), "--audit-next-proofs"])
            )
            if not qs:
                continue
            dump(file, {**tape, "requests": qs})
            inv = json.loads(subprocess.check_output([*cmd, str(n), "--recall", file]))[
                "recall_verdicts"
            ]
            missing = {
                k
                for _, k, owner, why in inv
                if owner is None and why == "off_reference"
            }
            if not missing:
                continue
            req = [q for q in qs if q["token"] in missing]
            observer = Observer(n, req)
            pol = EventGenerator(root, c, out, mode)
            pol.audit = observer
            audit = execute(
                root, c, study=pol, series=f"event-shadow/{mode}", limit=n, seconds=300
            )
            assert audit["termination"] == "schedule_end"
            replay = json.loads(subprocess.check_output([*cmd, str(n)]))
            assert audit["state_sha"] == replay["state_sha"], "observed prefix changed"
            result.update(
                first=n,
                missed=len(req),
                rules=dict(Counter(q["rule"] for q in req)),
                deepest=dict(Counter(k for _, k in observer.stage)),
            )
            break
    dump(out / f"omission-{c}-{mode}.json", result)
    print(result, flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--cases", nargs="+", required=True)
    p.add_argument("--modes", nargs="+", default=["B", "C", "D"])
    p.add_argument("--rep", type=int, default=4)
    a = p.parse_args()
    torch.set_num_threads(1)
    for case in a.cases:
        for mode in a.modes:
            diagnose(a.root, a.out, case, mode, a.rep)
