"""Transfer donor-only Bake layouts into the same real EggCC execution environment."""

import json
import os
from collections import Counter
from pathlib import Path

import torch

from cell_kv_runtime import native
from cell_kv_world import World
from competition_egg import egg
from constructible_study import TracePolicy
from foundation_fit import model
from foundation_world import folder
from partner_index_worlds import args
from region_bake import linked

CATS = ("primitive", "short", "medium", "multi")


def install(w, units, cat):
    # Pair the same roots across sizes. Require named static outputs at both boundaries.
    for u in units.values():
        if len(u) < 5 or any(not w.outputs[u[j][0]] for j in (1, 4)):
            continue
        if any(
            prev < 0 or prev >= j
            for j, (_, _, wires) in enumerate(u[1:5], 1)
            for prev, _ in wires
        ):
            continue  # Current KV suffix engine reads named internal outputs only.
        for size in {"primitive": (), "short": (2,), "medium": (5,), "multi": (2, 5)}[
            cat
        ]:
            body = u[:size]
            w.export_pc[len(w.layouts)] = min(w.outputs[body[-1][0]].values())
            w.layouts.append(body)


def run(a):
    manifest = Path(os.environ["ARTIFACT_ROOT"]) / "region-owner-1126/menu.json"
    audit = os.getenv("FC_RECEIPTS") == "1"
    donor = json.loads(manifest.read_text())
    out = folder(a)
    for case in os.getenv("FC_EGG", "fact loopfact sum-divisors").split():
        ir, align = egg(a, case)
        p = out / f"transfer-{case}.json"
        expected = {}
        if audit:
            expected = {(r["seed"], r["cat"]): r for r in json.loads(p.read_text())}
            p = out / f"receipt-check-{case}.json"
        rows = json.loads(p.read_text()) if p.exists() else []
        units = linked(json.loads((ir / "program.json").read_text()), donor)
        for seed in (71, 113):
            for rep in (0,) if audit else (0, 1):
                for cat in CATS if rep == 0 else reversed(CATS):
                    if audit and cat == "primitive":
                        continue
                    if any(
                        (r["cat"], r["seed"], r["rep"]) == (cat, seed, rep)
                        for r in rows
                    ):
                        continue
                    net = model(a, seed, 32)
                    net.load_state_dict(
                        torch.load(
                            out / f"model-{cat}-12-32-{seed}.pt", weights_only=True
                        )
                    )
                    w = World(ir, net.actor, entry_table=None, sides="")
                    install(w, units, cat)
                    pol = TracePolicy(net, True)
                    z = native(
                        a,
                        w,
                        reference=align,
                        policy=pol,
                        receipt_log=pol,
                        seed=193,
                        slots=6,
                        submit_pages=2,
                        receipt_memory=True,
                    )
                    if audit:
                        base = expected[seed, cat]
                        assert all(base[k] == z[k] for k in ("graph", "facts", "stats"))
                        receipts = Counter(
                            status
                            for _, page in pol.pages
                            for t, refs, status in page
                            if t >= w.primitives
                        )
                        assert sum(receipts.values()) == z["stats"]["higher_selected"]
                        z["higher_receipts"] = dict(receipts)
                    rows.append(
                        dict(
                            cat=cat,
                            seed=seed,
                            rep=rep,
                            case=case,
                            decode=pol.decode_s,
                            extra=len(w.layouts) - w.primitives,
                            neural=pol.count["signed"],
                            **z,
                        )
                    )
                    tmp = p.with_suffix(".tmp")
                    tmp.write_text(json.dumps(rows, separators=(",", ":")))
                    tmp.replace(p)
                    print(
                        case,
                        cat,
                        seed,
                        rep,
                        rows[-1]["extra"],
                        z["covered"],
                        flush=True,
                    )


if __name__ == "__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        run(args())
