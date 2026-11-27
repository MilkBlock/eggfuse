"""Post-run decomposition of inactive issues on complete autonomous EggCC trajectories."""

import json
import os
from collections import Counter
from pathlib import Path

import torch

from cell_kv_runtime import native
from cell_kv_world import World
from cell_transaction import STATUS
from competition_egg import egg
from constructible_study import TracePolicy
from foundation_egg_catalogue import install
from foundation_fit import model
from partner_index_worlds import args
from region_bake import linked
from trigger_training import MODES, directory


class PublishedPages:
    def __init__(self):
        self.pages = []

    def append(self, record):
        s, tokens, replies = record
        self.pages.append(
            (
                s["run"],
                s["menu"],
                tuple(p[3] for p in s["ports"]),
                s["rule_state"],
                tokens,
                [STATUS[r[1]] for r in replies],
            )
        )


def decompose(w, pages):
    rows = Counter()
    for run, menu, tables, flags, tokens, receipts in pages:
        tables = set(tables)
        support = {w.layouts[t][0][0] for t in menu}
        support = {r for r in support if all(v in tables for v in w.roles[r])}
        active = sum(flags[r][1] for r in support)
        kind = (
            "empty"
            if not support
            else "all-clean"
            if not active
            else "all-active"
            if active == len(support)
            else "mixed"
        )
        for j, ((t, _), status) in enumerate(zip(tokens, receipts, strict=True)):
            rid = w.layouts[t][0][0]
            assert rid in support
            rows[(kind, j, status)] += 1
    return [
        {"support": k, "slot": j, "status": s, "count": v}
        for (k, j, s), v in sorted(rows.items())
    ]


def main(a, case):
    out = directory(a)
    ir, align = egg(a, case)
    manifest = json.loads(
        (Path(os.environ["ARTIFACT_ROOT"]) / "region-owner-1126/menu.json").read_text()
    )
    units = linked(json.loads((ir / "program.json").read_text()), manifest)
    expected = json.loads((out / f"{case}-full.json").read_text())
    rows = []
    for mode in MODES:
        for seed in (71, 113):
            n = model(a, seed, 32)
            n.load_state_dict(torch.load(out / f"{mode}-{seed}.pt", weights_only=True))
            n.eval()
            n.rule_condition = mode
            n.physical = ("held", 0)
            w = World(ir, n.actor, entry_table=None, sides="")
            install(w, units, "multi")
            trace = PublishedPages()
            z = native(
                a,
                w,
                policy=TracePolicy(n, True),
                receipt_log=trace,
                receipt_memory=True,
                rule_state=True,
                slots=6,
                submit_pages=2,
                reference=align,
                seed=193,
            )
            base = next(
                r
                for r in expected
                if r["mode"] == mode and r["seed"] == seed and r["rep"] == -1
            )
            assert all(z[k] == base[k] for k in ("facts", "graph", "stats", "receipts"))
            rows.extend(
                r | {"case": case, "mode": mode, "seed": seed}
                for r in decompose(w, trace.pages)
            )
    (out / f"windows-{case}.json").write_text(json.dumps(rows))


if __name__ == "__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        main(args(), os.environ["TR_CASE"])
