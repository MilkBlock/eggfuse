"""Aggregate distinct counterfactual pairs, frozen probes and paired native execution."""

import csv
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean, median

from operand_read_probe import write


def groups(rows, keys):
    output = defaultdict(list)
    for r in rows:
        output[tuple(r[k] for k in keys)].append(r)
    return output


def report(src, dest):
    dest.mkdir(exist_ok=True, parents=True)
    diag = json.loads((src / "diagnostic.json").read_text())
    live = json.loads((src / "native.json").read_text())
    ranks = []
    performance = []
    for (label, arm, seed), rows in groups(diag, ("label", "arm", "seed")).items():
        pairs = defaultdict(dict)
        for r in rows:
            bits = r["bits"]
            if label == "position":
                key = (r["pool"], r["g"], r["o"], *bits[:2])
                axis = bits[2]
            else:
                key = (r["pool"], r["g"], r["o"], *bits)
                axis = r["wire"]
            pairs[key][axis] = r
        conflicts = []
        for pair in pairs.values():
            a, b = pair[0], pair[1]
            if a["gold"] != b["gold"]:
                conflicts.append(pair)
        part = [r for pair in conflicts for r in pair.values()]
        ranks.append(
            {
                "label": label,
                "arm": arm,
                "seed": seed,
                "pairs": len(conflicts),
                "flips": sum(
                    all(r["margin"] * (1 - 2 * r["gold"]) > 0 for r in pair.values())
                    for pair in conflicts
                ),
                "p_branch": mean(r["p_branch"] for r in part),
                "p_full": mean(r["p_full"] for r in part),
                "mean_query_gradient": mean(r["grad"] for r in part),
                "target_weight": mean(r["mass"] for r in part) if arm != "A" else None,
            }
        )
    index = {
        (
            r["label"],
            r["arm"],
            r["seed"],
            r["wire"],
            r["g"],
            r["o"],
            r["draw"],
            tuple(r["bits"]),
            r["block"],
        ): r
        for r in live
    }
    for (label, arm, seed), rows in groups(live, ("label", "arm", "seed")).items():
        trials = [r for r in rows if r["block"] == 0]
        eq = []
        disp = []
        for r in trials:
            k = (r["seed"], r["wire"], r["g"], r["o"], r["draw"], tuple(r["bits"]))
            repeat = index[label, arm, *k, 1]
            for f in ("facts", "graph", "stats", "hits", "ops"):
                assert r[f] == repeat[f]
            disp.append(abs(r["wall"] - repeat["wall"]) / r["wall"])
            ref = index[label, "A", *k, 0]
            if r["facts"] == ref["facts"] and r["graph"] == ref["graph"]:
                eq.append(
                    (r["wall"] + repeat["wall"])
                    / (ref["wall"] + index[label, "A", *k, 1]["wall"])
                )
        performance.append(
            {
                "label": label,
                "arm": arm,
                "seed": seed,
                "n": len(trials),
                "coverage": mean(r["coverage"] for r in trials),
                "ept": mean(r["ept"] for r in trials),
                "eps": mean(r["eps"] for r in rows),
                "paid": mean(r["stats"]["paid"] for r in trials),
                "first_full_hit": sum(r["hits"] for r in trials)
                / sum(r["slots"] for r in trials),
                "complete": sum(r["stats"]["higher_completed"] for r in trials),
                "matched": len(eq),
                "matched_wall_ratio": median(eq) if eq else None,
                "relative_spread": median(disp),
            }
        )
    write(dest / "diagnostic.csv", ranks)
    write(dest / "execution.csv", performance)
    with (src / "interventions.csv").open() as handle:
        reads = list(csv.DictReader(handle))
    write(
        dest / "interventions.csv",
        [
            {
                "seed": s,
                "mode": m,
                "n": len(rows),
                "both": sum(r["both"] == "True" for r in rows),
                "neither": sum(r["neither"] == "True" for r in rows),
            }
            for (s, m), rows in groups(reads, ("seed", "mode")).items()
        ],
    )
    for name in ("cost.csv", "early.csv"):
        (dest / name).write_bytes((src / name).read_bytes())
    # Keep the full posterior and gradient for a matched state and both static wirings per seed.
    sample = [
        r
        for r in diag
        if r["label"] == "known"
        and r["g"] == r["o"] == 0
        and r["pool"] == 81011
        and r["bits"] == [0, 0, 1]
    ]
    (dest / "weights.json").write_text(json.dumps(sample, indent=2) + "\n")
    files = list(src.glob("*.pt")) + list(src.glob("*.json")) + list(src.glob("*.csv"))
    manifest = {}
    for p in sorted(files):
        with p.open("rb") as f:
            manifest[p.name] = hashlib.file_digest(f, "sha256").hexdigest()
    for seed in (71, 113):
        p = src.parent / "rich" / f"C-{seed}-1680.pt"
        with p.open("rb") as f:
            manifest["../rich/" + p.name] = hashlib.file_digest(f, "sha256").hexdigest()
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    report(Path(sys.argv[1]), Path(sys.argv[2]))
