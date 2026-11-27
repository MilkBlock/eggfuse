"""Paired native outcomes and the effect of changing only how a page is sampled."""

import hashlib
import json
import sys
from pathlib import Path
from statistics import mean, median

from competition_results import groups, table


def run(src, d):
    native = []
    differences = []
    summary = []
    timings = []
    required = {
        f"live-{case}{suffix}.json"
        for case in ("mixed", "fact", "loopfact", "sum-divisors")
        for suffix in ("", "-cap12" if case == "mixed" else "-cap96")
    }
    missing = required - {p.name for p in src.glob("live-*.json")}
    if missing:
        raise ValueError(f"missing execution files: {sorted(missing)}")
    for p in (src / name for name in sorted(required)):
        case = p.stem[5:]
        rows = json.loads(p.read_text())
        expected = 384 if case.startswith("mixed") else 24
        if len(rows) != expected:
            raise ValueError(f"{case}: expected {expected} executions, got {len(rows)}")
        for (arm, mode), rs in groups(rows, ("arm", "mode")).items():
            reps = []
            disp = []
            for (seed, idx, draw), pair in groups(
                rs, ("seed", "index", "draw")
            ).items():
                a, b = pair
                assert all(
                    a[k] == b[k]
                    for k in ("ops", "facts", "graph", "stats", "attempts", "pending")
                )
                reps.append(a)
                disp.append(abs(a["wall"] - b["wall"]) / mean(z["wall"] for z in pair))
                native.append(
                    {
                        "case": case,
                        "arm": arm,
                        "mode": mode,
                        "seed": seed,
                        "index": idx,
                        "draw": draw,
                        "ops": a["ops"],
                        "paid": a["stats"]["paid"],
                        "attempts": a["attempts"],
                        "covered": a["covered"],
                        "reference": a["reference"],
                        "wall1": a["wall"],
                        "wall2": b["wall"],
                        "graph": a["graph"],
                    }
                )
            summary.append(
                {
                    "case": case,
                    "arm": arm,
                    "mode": mode,
                    "n": len(reps),
                    "coverage": mean(z["coverage"] for z in reps),
                    "covered": mean(z["covered"] for z in reps),
                    "reference": reps[0]["reference"],
                    "ept": mean(z["ept"] for z in reps),
                    "eps": mean(z["eps"] for z in rs),
                    "paid": mean(z["stats"]["paid"] for z in reps),
                    "wall": median(z["wall"] for z in rs),
                    "pair_spread": median(disp),
                    "higher_completed": mean(
                        z["stats"]["higher_completed"] for z in reps
                    ),
                }
            )
        for key, block in groups(rows, ("seed", "index", "draw", "block")).items():
            look = {(r["arm"], r["mode"]): r for r in block}
            for mode in ("iid", "unique"):
                comparisons = [(("blind", mode), ("visible", mode))]
                if mode == "iid":
                    comparisons.extend(
                        ((arm, "iid"), (arm, "unique"))
                        for arm in {r["arm"] for r in block}
                    )
                for baseline, changed in comparisons:
                    x, y = look[baseline], look[changed]
                    timings.append(
                        {
                            "case": case,
                            "seed": key[0],
                            "index": key[1],
                            "draw": key[2],
                            "block": key[3],
                            "baseline": "/".join(baseline),
                            "changed": "/".join(changed),
                            "same_graph_and_facts": x["graph"] == y["graph"]
                            and x["facts"] == y["facts"],
                            "wall_ratio": y["wall"] / x["wall"],
                            "ops_delta": y["ops"] - x["ops"],
                            "paid_delta": y["stats"]["paid"] - x["stats"]["paid"],
                        }
                    )
        for ab in groups(
            [r for r in rows if r["block"] == 0], ("seed", "index", "draw", "arm")
        ).values():
            x, y = sorted(ab, key=lambda r: r["mode"])

            def facts(r):
                return {json.dumps(v) for v in r["facts"]}

            l, r = facts(x), facts(y)
            differences.append(
                {
                    "case": case,
                    "arm": x["arm"],
                    "seed": x["seed"],
                    "index": x["index"],
                    "draw": x["draw"],
                    "same_graph": x["graph"] == y["graph"],
                    "common": len(l & r),
                    "lost": len(l - r),
                    "gained": len(r - l),
                }
            )
    table(d, "paired-timings", sorted(timings, key=lambda r: tuple(r.values())))
    curves = []
    for p in sorted(src.glob("curve-*.json")):
        _, arm, seed = p.stem.split("-")
        for step, ce, exposure in json.loads(p.read_text()):
            curves.append(
                {
                    "arm": arm,
                    "seed": seed,
                    "step": step,
                    "batch_ce": ce,
                    "exposures": exposure,
                }
            )
    table(d, "training", curves)
    table(d, "native", native)
    table(d, "scores", summary)
    table(d, "paired-facts", differences)
    for p in sorted([*src.glob("stall-*.json"), *src.glob("intervention-*.json")]):
        (d / p.name).write_bytes(p.read_bytes())
    sums = {}
    for p in sorted(src.iterdir()):
        if p.is_file():
            sums[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
    (d / "manifest.json").write_text(json.dumps(sums, indent=2) + "\n")


if __name__ == "__main__":
    run(*map(Path, sys.argv[1:]))
