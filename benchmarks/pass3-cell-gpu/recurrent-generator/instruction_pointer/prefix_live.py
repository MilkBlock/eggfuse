"""Independent native execution; no audited targets available to any online policy."""

import json
import os
from pathlib import Path

import torch

from cell_kv_runtime import native
from cell_kv_world import World
from competition_egg import egg
from foundation_egg_catalogue import install
from partner_index_worlds import args
from prefix_corpus import folder
from prefix_train import fitted
from region_bake import linked
from variable_binding_execution import SparsePolicy
from variable_completion import CompletionPolicy


def run(a, case):
    ir, align = egg(a, case)
    d = folder(a)
    donor = json.loads(
        (Path(os.environ["ARTIFACT_ROOT"]) / "region-owner-1126/menu.json").read_text()
    )
    arms = [
        ("base", 0, False),
        ("sparse", 0, False),
        ("rel", 0, False),
        ("base", 71, False),
        ("rel", 71, False),
        ("rel", 113, False),
        ("base", 71, True),
        ("rel", 113, True),
        ("base", 0, True),
        ("rel", 71, True),
    ]
    paid = os.getenv("PREFIX_PAID") == "1"
    stem = "paid" if paid else "live"
    serial = os.getenv("PREFIX_SERIAL") == "1"
    if serial:
        arms = [("base", 0, False), ("sparse", 0, False), ("rel", 71, False)]
    if paid:
        arms = [
            ("base", 0, True),
            ("base", 71, True),
            ("rel", 0, True),
            ("rel", 71, True),
            ("rel", 113, True),
        ]
    for rep in (2, 3) if serial else (0, 1):
        for arm, seed, unique in arms if rep % 2 == 0 else reversed(arms):
            path = d / f"{stem}-{case}-{arm}-{seed}-{int(unique)}-{rep}.json"
            if path.exists():
                continue
            n = fitted(a, case, arm, seed)
            w = World(ir, n.actor, entry_table=None, sides="")
            install(w, linked(w.prog, donor), "multi")
            pol = (
                SparsePolicy(n, None, a, a.data / case)
                if arm == "sparse"
                else CompletionPolicy(n, unique, None, False)
            )
            x = native(
                a,
                w,
                policy=pol,
                receipt_log=pol,
                receipt_memory=True,
                slots=6,
                submit_pages=2,
                reference=align,
                seed=193,
                rule_state=True,
                paid_limit=96 if paid else None,
            )
            x.update(
                case=case,
                arm=arm,
                seed=seed,
                unique=unique,
                rep=rep,
                generate_s=pol.decode_s,
                prepare_s=pol.prepare_s,
                count=pol.count,
                publication_s=getattr(pol, "publication_s", 0),
            )
            if rep:
                other = json.loads(
                    (d / f"{stem}-{case}-{arm}-{seed}-{int(unique)}-0.json").read_text()
                )
                assert all(other[k] == x[k] for k in ("facts", "graph", "stats", "ops"))
            path.write_text(json.dumps(x, separators=(",", ":")))
            print(case, arm, seed, unique, rep, x["covered"], x["ops"], flush=True)


if __name__ == "__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        run(args(), os.environ["TR_CASE"])
