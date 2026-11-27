"""Keep exact effect classes, unique named tokens, and committed collective effects separate."""

import csv
import hashlib
import json
import pickle
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median


def groups(rows, keys):
    out = defaultdict(list)
    for r in rows:
        out[tuple(r[k] for k in keys)].append(r)
    return out


def table(d, name, rows):
    if not rows:
        return
    with (d / (name + ".csv")).open("w") as f:
        w = csv.DictWriter(
            f, dict.fromkeys(k for r in rows for k in r), lineterminator="\n", restval=0
        )
        w.writeheader()
        w.writerows(rows)


def avg(d, src, prefix, keys, fields):
    rows = []
    for ix, b in groups(src, keys).items():
        rows.append(
            {
                **dict(zip(keys, ix)),
                "n": len(b),
                **{k: mean(r.get(k, 0) for r in b) for k in fields},
            }
        )
    table(d, prefix, rows)


def export(src, d):
    d.mkdir(exist_ok=True, parents=True)
    read = lambda name: json.loads((src / (name + ".json")).read_text())
    kinds = ["single", "mixed", "arity", "fork", "aliases"]
    corpus = []
    for k in kinds:
        r = [
            row
            for p in sorted(src.glob(f"train-{k}-*.pkl"))
            for row in pickle.loads(p.read_bytes())
        ]
        corpus.append(
            {
                "kind": k,
                "states": len(r),
                "trace_occurrences": sum(len(ts) for _, ts, _, _ in r),
                "signed_candidates": sum(len(v) + u for _, _, v, u in r),
                "verified_named": sum(len(v) for _, _, v, _ in r),
                "effect_classes": sum(len(set(v.values())) for _, _, v, _ in r),
                "unlabeled": sum(u for _, _, _, u in r),
                "trace_unverified": sum(
                    sum(t not in v for t in ts) for _, ts, v, _ in r
                ),
                "extra_verified": sum(len(v.keys() - set(ts)) for _, ts, v, _ in r),
            }
        )
    table(d, "corpus", corpus)
    exposures = []
    for p in sorted(src.glob("*-curve.json")):
        arm, seed, _ = p.stem.split("-")
        for step, ce, counts in json.loads(p.read_text()):
            exposures.append(
                dict(
                    arm=arm,
                    seed=seed,
                    step=step,
                    ce=ce,
                    total=sum(counts.values()),
                    **counts,
                )
            )
    table(d, "exposure", exposures)
    mass = read("mass")
    avg(
        d,
        mass,
        "mass",
        ("kind", "arm", "seed"),
        ["arity0", "arity1", "arity2", "verified0", "verified1", "verified2", "start"],
    )
    curves = read("curves")
    curvefields = [
        "attempts",
        "signed",
        "physical_dup",
        "known_effects",
        "union_facts",
        *[f"{metric}{j}" for j in range(3) for metric in ("draw", "found", "effects")],
        "facts_StartMark",
        "facts_Together",
        "facts_Seen",
    ]
    avg(d, curves, "discovery", ("kind", "arm", "mode", "budget"), curvefields)
    batch = read("batches")
    for r in batch:
        r.update({"facts_" + k: v for k, v in r["new_by_table"].items()})
    avg(
        d,
        batch,
        "native-batches",
        ("kind", "arm", "mode", "budget"),
        [
            "paid",
            "signed",
            "ops",
            "actual",
            "facts_StartMark",
            "facts_Together",
            "facts_Seen",
        ],
    )
    native = read("live")
    summary = []
    by_table = []
    for (kind, arm, mode, seed), rs in groups(
        native, ("kind", "arm", "mode", "seed")
    ).items():
        pairs = groups(rs, ("case", "draw")).values()
        cases = []
        spread = []
        for a, b in pairs:
            assert all(a[x] == b[x] for x in ("facts", "graph", "stats", "ops"))
            cases.append(a)
            spread.append(abs(a["wall"] - b["wall"]) / mean([a["wall"], b["wall"]]))
        summary.append(
            {
                "kind": kind,
                "arm": arm,
                "mode": mode,
                "seed": seed,
                "cases": len(cases),
                "coverage": mean(x["coverage"] for x in cases),
                "ept": mean(x["ept"] for x in cases),
                "eps": mean(x["eps"] for x in rs),
                "paid": mean(x["stats"]["paid"] for x in cases),
                "signed": mean(x["stats"]["neural_tokens"] for x in cases),
                "higher": mean(x["stats"]["higher_completed"] for x in cases),
                "attempts": mean(x["attempts"] for x in cases),
                "kernels": mean(x["kernels"] for x in cases),
                "pair_spread": median(spread),
            }
        )
        for x in cases:
            by_table.append(
                dict(
                    kind=kind,
                    arm=arm,
                    mode=mode,
                    seed=seed,
                    case=x["case"],
                    draw=x["draw"],
                    **Counter(t for t, v in x["facts"]),
                )
            )
    table(d, "native", summary)
    table(d, "facts", by_table)
    refs = {(x["kind"], x["case"]): x["by_table"] for x in read("reference-sets")}
    recall = []
    coexist = []
    for (kind, arm, mode), rows in groups(
        [r for r in native if r["block"] == 0], ("kind", "arm", "mode")
    ).items():
        joint = Counter()
        categories = Counter()
        denominators = Counter()
        for x in rows:
            by = Counter(t for t, v in x["facts"])
            categories.update(by)
            denominators.update(refs[kind, x["case"]])
            both = by["StartMark"] > 0 and by["Together"] > 0
            joint["with_zero"] += by["StartMark"] > 0
            joint["with_two"] += by["Together"] > 0
            joint["both"] += both
            joint["both_and_higher"] += both and x["stats"]["higher_completed"] > 0
        if "StartMark" in denominators and "Together" in denominators:
            coexist.append(dict(kind=kind, arm=arm, mode=mode, n=len(rows), **joint))
        for tab, den in sorted(denominators.items()):
            recall.append(
                {
                    "kind": kind,
                    "arm": arm,
                    "mode": mode,
                    "table": tab,
                    "actual": categories[tab],
                    "reference": den,
                    "recall": categories[tab] / den,
                }
            )
    table(d, "category-recall", recall)
    table(d, "coexistence", coexist)
    same = []
    for (k, arm, seed), rs in groups(native, ("kind", "arm", "seed")).items():
        ratios = []
        for ab in groups(rs, ("case", "draw", "block")).values():
            a, b = sorted(ab, key=lambda r: r["mode"])
            if a["graph"] == b["graph"] and a["facts"] == b["facts"]:
                ratios.append(b["wall"] / a["wall"])
        same.append(
            {
                "kind": k,
                "arm": arm,
                "seed": seed,
                "matches": len(ratios) // 2,
                "possible": len(rs) // 4,
                "median_unique_over_iid": median(ratios) if ratios else "",
            }
        )
    table(d, "same-graph", same)
    egg = []
    matches = []
    for p in sorted((src / "egg").glob("*/results*.json")):
        if "pilot" in p.name:
            continue
        allruns = json.loads(p.read_text())
        for r in allruns:
            r.setdefault("mode", "iid")
        for pair in groups(allruns, ("arm", "seed", "mode")).values():
            a, b = pair
            assert all(a[k] == b[k] for k in ("graph", "facts", "ops", "covered"))
        for (seed, block), runs in groups(allruns, ("seed", "block")).items():
            if block:
                continue
            base = next(
                x
                for x in runs
                if x["arm"] == ("B" if "-draw" in p.name else "A")
                and x["mode"] == "iid"
            )
            for x in runs:
                left = set(base["facts"])
                right = set(x["facts"])
                matches.append(
                    {
                        "case": x["case"],
                        "seed": seed,
                        "baseline": base["arm"],
                        "arm": x["arm"],
                        "mode": x["mode"],
                        "common": len(left & right),
                        "lost": len(left - right),
                        "gained": len(right - left),
                        "same_graph": x["graph"] == base["graph"],
                    }
                )
        for r in allruns:
            r["mode"] = r.get("mode", "iid")
            egg.append(
                {
                    "file": p.name,
                    "case": r["case"],
                    "arm": r["arm"],
                    "seed": r["seed"],
                    "mode": r["mode"],
                    "block": r["block"],
                    "covered": r["covered"],
                    "reference": r["reference"],
                    "ops": r["ops"],
                    "coverage": r["coverage"],
                    "ept": r["ept"],
                    "eps": r["eps"],
                    "paid": r["stats"]["paid"],
                    "attempts": r["attempts"],
                    "graph": r["graph"],
                }
            )
    table(d, "eggcc", egg)
    table(d, "eggcc-facts", matches)
    avg(
        d,
        egg,
        "eggcc-summary",
        ("file", "case", "arm", "mode"),
        ["covered", "reference", "coverage", "ept", "eps", "paid", "attempts"],
    )
    files = (
        list(src.glob("*.json"))
        + list(src.glob("*.pt"))
        + list(src.glob("*.pkl"))
        + list((src / "egg").glob("*/results*.json"))
    )
    files += list((src / "egg").glob("*/program.json"))
    (d / "manifest.json").write_text(
        json.dumps(
            {
                str(p.relative_to(src)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(files)
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    export(*map(Path, sys.argv[1:]))
