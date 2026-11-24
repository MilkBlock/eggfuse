"""Direct B template refinement from the event, before its first parent search."""

import argparse
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch

from deep_ripsat import deployable
from event_generator import EventGenerator
from higher_replacement import Policy, send
from protocol_experiment import dump
from recursive_coverage import Target, snapshot
from recursive_train import folder, read
from int_parameters import link_layouts
from ripsat_policy import CellScorer
from transaction_native import execute


class DeepTemplates:
    def __init__(self, program, catalog_dir, full=False, size=None, *, concrete_only=False):
        catalog = read(catalog_dir / "catalog.json")
        checkpoint = torch.load(catalog_dir / "event-gnn.pt", weights_only=True)
        width = checkpoint["codes"].shape[1]
        self.model = CellScorer(width).eval()
        self.model.load_state_dict(checkpoint["model"])
        self.encoder = torch.nn.Linear(16, width)
        self.encoder.load_state_dict(checkpoint["encoder"])
        self.menu = defaultdict(list)
        self.cat = SimpleNamespace(units={})
        if concrete_only:
            catalog = {k: catalog[k] for k in ("signatures", "layouts")}
        for i, unit in link_layouts(program, catalog, size):
            if full or deployable(unit):
                self.cat.units[i] = unit
                self.menu[unit[0][0]].append(i)
        self.codes = checkpoint["codes"]
        self.groups = defaultdict(lambda: "deep")
        self.waiting = []
        self.expected, self.completed, self.internal = set(), set(), set()

    def start(self, rd, pub, txn, rules, stats):
        self.count = stats
        self.done = Policy.advance(self, rd, pub, txn, rules)

    def choose(self, r, j, ix, mem, woke):
        self.mem = mem
        self.choice = {}
        menu = self.menu.get(r)
        if not menu or woke:
            return
        events = (
            mem.bank(mem.roles[r][j]).vec[ix]
            if j >= 0
            else np.zeros((len(ix), 16), np.float32)
        )
        x = self.encoder(torch.from_numpy(events))
        for i, row in zip(ix, x, strict=True):
            scores = self.model(row.expand(len(menu), -1), self.codes[menu])[:, 1]
            best = int(scores.argmax())
            if scores[best] > 0:
                self.choice[int(i)] = menu[best]
        self.count["higher_event_scores"] += len(events) * len(menu)
        self.count["higher_event_choices"] += len(self.choice)

    def issue(self, r, roots, refs, txn):
        for start in range(0, len(refs), txn.capacity):
            batch = refs[start : start + txn.capacity]
            sources = roots[start : start + txn.capacity]
            if self.done.get(r):
                keep = [tuple(map(tuple, row)) not in self.done[r] for row in batch]
                self.count["replaced_requests"] += len(batch) - sum(keep)
                batch, sources = batch[keep], sources[keep]
            if not len(batch):
                continue
            responses = send(txn, r, batch)
            for idx in np.flatnonzero(responses[:, 1] == 0):
                uid = self.choice.get(int(sources[idx]))
                if uid is not None:
                    tok = int(responses[idx, 0])
                    self.begin(uid, batch[idx], tok, txn)

    def begin(self, uid, row, tok, txn):
        self.expected.add(tok)
        self.waiting.append((uid, tuple(map(tuple, row)), (tok,), {}))
        self.count["higher_started"] += 1


def run(root, out, case, deep, rep, *, concrete_only=False):
    policy = EventGenerator(root, case, Path("run-recall/cell-events"), "B")
    d = folder(root, case)
    if deep:
        if deep in (2, 3):
            from deep_event_boundary import FullTemplates

            policy.higher = FullTemplates(
                read(d / "program.json"), out, size=4096 if deep == 3 else None,
                concrete_only=concrete_only
            )
        else:
            policy.higher = DeepTemplates(read(d / "program.json"), out, concrete_only=concrete_only)
    series = f"deep-ripsat/{int(deep)}/{rep}"
    result = execute(root, case, study=policy, seconds=300, series=series)
    work = root / series / (case + "-stream-multi")
    align = work / "align.json"
    t = Target(
        read(d / "program.json"), snapshot(root, d, "reference", "-", None, align)[0]
    )
    initial = t.match(snapshot(root, d, "reference", "-", 0, align)[0])
    result.update(
        facts=len(t.match(read(work / "state.json")) - initial),
        reference=len(t.gold) - len(initial),
    )
    result.pop("trace")
    dump(out / f"{case}-{int(deep)}-{rep}.json", result)
    print(case, deep, rep, result["facts"], result["paid"], result["wall"], flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("cases", nargs="+")
    p.add_argument("--reps", type=int, default=4)
    p.add_argument(
        "--arms", nargs="+", type=int, choices=[0, 1, 2, 3], default=[0, 1, 3, 2]
    )
    p.add_argument("--concrete-only", action="store_true", help="restrict linking to exact legacy rule signatures")
    p.add_argument("--offset", type=int, default=0)
    a = p.parse_args()
    torch.set_num_threads(1)
    for i in range(a.reps):
        for case in a.cases:
            for arm in a.arms if i % 2 == 0 else reversed(a.arms):
                run(a.root, a.out, case, arm, a.offset + i, concrete_only=a.concrete_only)
