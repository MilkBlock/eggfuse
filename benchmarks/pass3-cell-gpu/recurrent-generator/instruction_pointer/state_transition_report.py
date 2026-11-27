"""Export trajectory-level facts, exact-budget counts and paired wall-time dispersion."""

import hashlib
import json
import sys
from pathlib import Path
from statistics import mean, median

from competition_results import groups, table


def summarize(src, d):
    idle = []
    for path in sorted(src.glob("idle-*.json")):
        for i, r in enumerate(json.loads(path.read_text())):
            idle.append(
                {
                    "case": path.stem[5:],
                    "index": i,
                    "covered": r["covered"],
                    "ops": r["ops"],
                    "paid": r["stats"]["paid"],
                    "graph": r["graph"],
                }
            )
    table(d, "idle", idle)
    native = []
    rows = []
    intersections = []
    matched = []
    for f in sorted(src.glob("live-*.json")):
        raw = json.loads(f.read_text())
        for r in raw:
            r.setdefault("slot_limit", None)
            r.setdefault("offered", None)
        for (case, arm, mode, slots, cap, limit), rs in groups(
            raw, ("case", "arm", "mode", "slots", "cap", "slot_limit")
        ).items():
            representatives = []
            timing = []
            for (seed, i, draw), pair in groups(rs, ("seed", "index", "draw")).items():
                a, b = pair
                assert all(
                    a[k] == b[k]
                    for k in ("facts", "graph", "ops", "stats", "attempts", "pending")
                )
                representatives.append(a)
                timing.append(
                    abs(a["wall"] - b["wall"]) / mean(z["wall"] for z in pair)
                )
                native.append(
                    {
                        "case": case,
                        "arm": arm,
                        "mode": mode,
                        "slots": slots,
                        "cap": cap,
                        "limit": limit,
                        "seed": seed,
                        "index": i,
                        "draw": draw,
                        "paid": a["stats"]["paid"],
                        "attempts": a["attempts"],
                        "ops": a["ops"],
                        "covered": a["covered"],
                        "reference": a["reference"],
                        "graph": a["graph"],
                        "wall1": a["wall"],
                        "wall2": b["wall"],
                        "pending": a["pending"],
                    }
                )
            rows.append(
                {
                    "case": case,
                    "arm": arm,
                    "mode": mode,
                    "slots": slots,
                    "paid_cap": cap,
                    "slot_cap": limit,
                    "runs": len(representatives),
                    "exact_budget": sum(
                        (cap is not None and x["stats"]["paid"] == cap)
                        or (limit is not None and x["offered"] == limit)
                        for x in representatives
                    ),
                    "coverage": mean(x["coverage"] for x in representatives),
                    "covered": mean(x["covered"] for x in representatives),
                    "ept": mean(x["ept"] for x in representatives),
                    "eps": mean(x["eps"] for x in rs),
                    "wall": median(x["wall"] for x in rs),
                    "ops": mean(x["ops"] for x in representatives),
                    "paid": mean(x["stats"]["paid"] for x in representatives),
                    "attempts": mean(x["attempts"] for x in representatives),
                    "completed_higher": mean(
                        x["stats"]["higher_completed"] for x in representatives
                    ),
                    "pair_spread": median(timing),
                }
            )
        for rr in groups(
            [r for r in raw if r["block"] == 0],
            ("case", "seed", "index", "draw", "slots", "cap", "slot_limit"),
        ).values():
            for arm, rrr in groups(rr, ("arm",)).items():
                a, b = sorted(rrr, key=lambda r: r["mode"])
                conv = lambda r: {
                    json.dumps(x, separators=(",", ":")) for x in r["facts"]
                }
                left, right = conv(a), conv(b)
                intersections.append(
                    {
                        "case": a["case"],
                        "seed": a["seed"],
                        "index": a["index"],
                        "draw": a["draw"],
                        "arm": a["arm"],
                        "slots": a["slots"],
                        "paid_cap": a["cap"],
                        "slot_cap": a["slot_limit"],
                        "common": len(left & right),
                        "lost": len(left - right),
                        "gained": len(right - left),
                        "same_graph": a["graph"] == b["graph"],
                    }
                )
        for (case, arm, slots, cap, limit), all_runs in groups(
            raw, ("case", "arm", "slots", "cap", "slot_limit")
        ).items():
            if cap is None:
                continue
            metrics = []
            for pair in groups(all_runs, ("seed", "index", "draw", "block")).values():
                x, y = sorted(pair, key=lambda r: r["mode"])
                if x["stats"]["paid"] == y["stats"]["paid"] == cap:
                    metrics.append((x, y))
            matched.append(
                {
                    "case": case,
                    "arm": arm,
                    "slots": slots,
                    "paid_cap": cap,
                    "paired_runs": len(metrics) // 2,
                    **{
                        key + "_" + mode: mean(m[j][key] for m in metrics)
                        if metrics
                        else ""
                        for j, mode in enumerate(("iid", "unique"))
                        for key in ("coverage", "ept", "eps")
                    },
                }
            )
    exposures = []
    for p in sorted(src.glob("*-curve.json")):
        arm, seed, _ = p.stem.split("-")
        for step, ce, counts in json.loads(p.read_text()):
            exposures.append(
                {
                    "arm": arm,
                    "seed": seed,
                    "step": step,
                    "complete_ce": ce,
                    "exposures": sum(counts.values()),
                    **counts,
                }
            )
    table(d, "training", exposures)
    table(d, "same-paid", matched)
    table(d, "native", native)
    table(d, "budget-curves", rows)
    table(d, "draw-facts", intersections)
    paths = sorted([*src.glob("*.pkl"), *src.glob("*.pt"), *src.glob("*.json")])
    (d / "manifest.json").write_text(
        json.dumps(
            {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    summarize(*map(Path, sys.argv[1:]))
