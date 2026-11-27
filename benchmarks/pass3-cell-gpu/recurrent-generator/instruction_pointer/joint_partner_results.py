"""Summarize native trials by size, with a separate same-graph paired timing table."""

import csv
import hashlib
from pathlib import Path
from collections import defaultdict
from statistics import mean, median, stdev
import shutil
import sys
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def load(src, name):
    with (src / (name + ".csv")).open() as f:
        return list(csv.DictReader(f))


def save(path, data):
    with path.open("w") as f:
        w = csv.DictWriter(f, fieldnames=list(data[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(data)


def grouped(rows, keys, fields):
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(row[k] for k in keys)].append(row)
    out = []
    for key, values in sorted(groups.items()):
        item = dict(zip(keys, key), observations=len(values))
        for f in fields:
            v = [float(r[f]) for r in values if r[f] != ""]
            item[f] = mean(v) if v else ""
        out.append(item)
    return out


def report(src, dst):
    dst.mkdir(exist_ok=True, parents=True)
    raw = load(src, "snapshot-trials")
    assert len(raw) == 4320
    qs = [
        "first",
        "second",
        "third",
        "complete",
        "hits",
        "ops",
        "top1_all",
        "prior",
        "gap",
        "root_rank",
        "true_kernel",
        "wrong_kernel_sum",
        "wrong_kernel_max",
        "wrong_log_partition_minus_right",
    ]
    g = grouped(raw, ["kind", "size", "arm"], qs)
    save(dst / "snapshots.csv", g)
    twins = defaultdict(list)
    for row in raw:
        if row["kind"] in ("two", "three"):
            key = tuple(row[k] for k in ("kind", "size", "arm", "seed", "instance"))
            twins[key].append(row)
    twin_trials = []
    for (kind, size, arm, _, _), pair in twins.items():
        assert sorted(r["flip"] for r in pair) == ["0", "1"]
        twin_trials.append(
            dict(
                kind=kind,
                size=size,
                arm=arm,
                both_top1=int(all(int(r["top1_all"]) for r in pair)),
            )
        )
    save(
        dst / "twins.csv", grouped(twin_trials, ["kind", "size", "arm"], ["both_top1"])
    )
    save(dst / "seeds.csv", grouped(raw, ["kind", "size", "arm", "seed"], qs))
    for file, keys, fields in [
        (
            "stress",
            ["arm", "side", "roots", "partners"],
            [
                "first",
                "second",
                "complete",
                "hits",
                "prior",
                "true_kernel",
                "wrong_kernel_sum",
                "wrong_kernel_max",
                "gap",
                "root_rank",
                "wrong_log_partition_minus_right",
            ],
        ),
        (
            "context",
            ["arm", "n", "context", "copy"],
            ["last_root", "prior", "message", "root", "second"],
        ),
        (
            "challenge",
            ["case", "arm", "n", "mode"],
            ["root", "complete", "hits", "ops"],
        ),
        ("online", ["kind", "size", "arm"], ["coverage", "ept", "eps", "seconds"]),
        ("copy-online", ["size", "arm", "copy"], ["ops", "ept", "eps", "seconds"]),
        ("budget", ["size", "arm", "paid"], ["coverage", "ept", "eps", "seconds"]),
        ("cpu", ["kind", "size", "arm"], ["coverage", "ept", "eps", "seconds"]),
    ]:
        rs = load(src, file)
        save(dst / (file + ".csv"), grouped(rs, keys, fields))
    rs = load(src, "online")
    assert len(rs) == 3360
    comparisons = defaultdict(dict)
    for r in rs:
        comparisons[
            r["seed"], r["kind"], int(r["size"]), r["instance"], r["flip"], r["block"]
        ][r["arm"]] = r
    by = defaultdict(list)
    for (_, kind, n, *_), arms in comparisons.items():
        x = arms["independent"]
        for arm in ("cell", "tensor", "wide"):
            y = arms[arm]
            by[kind, n, arm].append(
                float(y["seconds"]) / float(x["seconds"])
                if int(x["ops"]) and x["graph"] == y["graph"]
                else None
            )
    pairs = []
    for (kind, n, arm), ratios in sorted(by.items()):
        t = [v for v in ratios if v is not None]
        pairs.append(
            dict(
                kind=kind,
                n=n,
                arm=arm,
                total=len(ratios),
                both_complete=len(t),
                median_ratio=median(t) if t else "",
                sd=stdev(t) if len(t) > 1 else "",
            )
        )
    save(dst / "same-graph.csv", pairs)
    for file in ("fit.csv", "components.csv", "updates.csv", "manifest.json"):
        shutil.copyfile(src / file, dst / file)
    weights = [
        dict(name=p.name, sha256=hashlib.sha256(p.read_bytes()).hexdigest())
        for p in sorted((src / "weights").glob("*.pt"))
    ]
    save(dst / "weights.csv", weights)
    fig, axes = plt.subplots(1, 2, figsize=(9.4, 3.7), constrained_layout=True)
    for ax, kind in zip(axes, ("two", "chain")):
        for arm, label in [
            ("independent", "Separate fields"),
            ("cell", "Joint row, 128"),
            ("tensor", "Tensor, 128"),
            ("wide", "Tensor, 1024"),
            ("dense", "Dense diagnostic"),
        ]:
            data = sorted(
                [x for x in g if x["kind"] == kind and x["arm"] == arm],
                key=lambda x: int(x["size"]),
            )
            ax.plot(
                [int(x["size"]) for x in data],
                [x["complete"] * 100 for x in data],
                marker="o",
                ms=3,
                label=label,
            )
        ax.set(
            xscale="log",
            yscale="log",
            xlabel="Rows per role",
            ylabel="Valid complete token probability (%)",
            title={"two": "Two shared fields", "chain": "Three-parent chain"}[kind],
        )
        ax.grid(alpha=0.22)
    axes[0].legend(fontsize=7)
    fig.savefig(dst / "binding-scale.png", dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    report(*map(Path, sys.argv[1:]))
