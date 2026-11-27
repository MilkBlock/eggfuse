"""Write native trial tables, paired same-graph costs and a conditional/free curve."""

import csv
import json
import hashlib
import shutil
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean, median, stdev

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def rows(p):
    with p.open() as f:
        return list(csv.DictReader(f))


def save(p, rs):
    with p.open("w") as f:
        w = csv.DictWriter(f, fieldnames=list(rs[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rs)


def aggregate(data, keys, metrics):
    by = defaultdict(list)
    for r in data:
        by[tuple(r[k] for k in keys)].append(r)
    results = []
    for key, g in sorted(by.items()):
        row = dict(zip(keys, key))
        for m in metrics:
            values = [float(x[m]) for x in g if x[m] != ""]
            row[m] = mean(values) if values else ""
        row["n"] = len(g)
        results.append(row)
    return results


def summarize(src, dest):
    dest.mkdir(exist_ok=True, parents=True)
    for name in (
        "training",
        "live",
        "guard-fit",
        "guards",
        "split-witness",
        "root-cost",
        "cpu",
    ):
        shutil.copyfile(src / f"{name}.csv", dest / f"{name}.csv")
    metrics = [
        "first",
        "second",
        "full",
        "hit",
        "recall32",
        "top1",
        "guard_reject",
        "prior_mass",
        "normalized_mass",
        "energy_gap",
        "reverse_error",
    ]
    trials = rows(src / "snapshots.csv")
    assert len(trials) == 4038
    save(
        dest / "snapshots.csv",
        aggregate(
            trials, ["split", "layout", "size", "domain", "arm", "seed"], metrics
        ),
    )
    eq = [r for r in trials if r["layout"].startswith("eq") and r["split"] == "test"]
    core = aggregate(eq, ["size", "arm"], metrics)
    save(dest / "equality.csv", core)
    save(
        dest / "calibration.csv",
        aggregate(
            rows(src / "calibration.csv"),
            ["size", "model", "seed"],
            ["raw", "conditional_only", "prior"],
        ),
    )
    live = rows(src / "live.csv")
    assert len(live) == 432 and len(rows(src / "guards.csv")) == 216
    save(
        dest / "live-summary.csv",
        aggregate(live, ["size", "arm"], ["coverage", "ept", "eps", "seconds", "paid"]),
    )
    by = defaultdict(dict)
    for r in live:
        by[r["size"], r["instance"], r["seed"], r["block"]][r["arm"]] = r
    pairs = []
    for size in sorted({r["size"] for r in live}, key=int):
        ratios = []
        for k, v in by.items():
            if k[0] != size:
                continue
            x, y = v["field"], v["pool"]
            if x["graph"] == y["graph"] and int(x["ops"]) > 0:
                ratios.append(float(y["seconds"]) / float(x["seconds"]))
        pairs.append(
            dict(
                size=size,
                same_graph_with_gain=len(ratios),
                pairs=18,
                median_wall_ratio=median(ratios) if ratios else "",
                sd=stdev(ratios) if len(ratios) > 1 else "",
            )
        )
    save(dest / "paired.csv", pairs)
    weights = [
        dict(checkpoint=p.name, sha256=hashlib.sha256(p.read_bytes()).hexdigest())
        for p in sorted((src / "weights").glob("*.pt"))
    ]
    save(dest / "weights.csv", weights)
    train = sorted((src / "worlds/fit").glob("*/ok.json"))
    assert len(train) == 384
    (dest / "corpus.json").write_text(
        json.dumps(
            {
                "independent_main_training_states": len(train),
                "verified_remaining_main_targets": sum(
                    len(json.loads(p.read_bytes())["gold"]) for p in train
                ),
                "guard_training_programs": 48,
                "snapshot_pages": len(trials),
                "requests_per_native_page": 32,
            }
        )
        + "\n"
    )
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.6), constrained_layout=True)
    for arm, label in (
        ("field", "One-way fields"),
        ("joint", "Dense joint (diagnostic)"),
        ("pool", "Pooled fields"),
    ):
        g = sorted([r for r in core if r["arm"] == arm], key=lambda r: int(r["size"]))
        for ax, m, title in zip(
            axes,
            ("first", "full"),
            ("Productive first-parent mass", "Complete valid token mass"),
        ):
            ax.plot(
                [int(r["size"]) for r in g],
                [100 * r[m] for r in g],
                marker="o",
                ms=3,
                label=label,
            )
            ax.set(
                xscale="log",
                yscale="log",
                title=title,
                xlabel="Same-type cells",
                ylabel="Probability (%)",
            )
            ax.grid(alpha=0.22)
    axes[0].legend(fontsize=8)
    fig.savefig(dest / "discovery.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    summarize(*map(Path, sys.argv[1:]))
