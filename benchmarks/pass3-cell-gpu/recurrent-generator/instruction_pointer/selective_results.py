"""Export text results from raw trials. Runs are nested by filler, flip and training seed."""

from collections import defaultdict
from pathlib import Path
import csv
import hashlib
import shutil
from statistics import mean, median, stdev
import sys
import numpy as np


def load(src, f):
    with (src / (f + ".csv")).open() as inp:
        return list(csv.DictReader(inp))


def save(dst, f, rows):
    with (dst / (f + ".csv")).open("w") as out:
        w = csv.DictWriter(out, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def groups(rows, cols):
    data = defaultdict(list)
    for r in rows:
        data[tuple(r[c] for c in cols)].append(r)
    return data


def average(rows, cols, fields):
    result = []
    for key, rs in sorted(groups(rows, cols).items()):
        out = dict(zip(cols, key), observations=len(rs))
        for k in fields:
            values = [float(r[k]) for r in rs if r[k] != ""]
            out[k] = mean(values) if values else ""
        result.append(out)
    return result


def main(src, dst):
    dst.mkdir(parents=True, exist_ok=True)
    expected_trials = {
        "frozen": 2400,
        "controls": 960,
        "replication": 864,
        "online": 1188,
        "near-online": 336,
        "budget": 432,
        "fresh-online": 96,
    }
    for table, count in expected_trials.items():
        actual = len(load(src, table))
        if actual != count:
            raise ValueError(f"{table}: expected {count} trials, found {actual}")

    for fn, keys, vals in [
        ("topology", "kind n mode", "first complete"),
        (
            "kernel",
            "n scope",
            "correct maximum gap mass p50 p95 p99 top1_share top8_share ratio_above_half half_signal_share",
        ),
        ("oracle-aggregation", "n mode", "root rank margin"),
        (
            "frozen",
            "n side kind arm copy",
            "first second third complete hits root_rank",
        ),
        ("controls", "n domain arm mode res", "first second complete"),
        ("replication", "domain arm copy", "first second complete rank"),
    ]:
        rs = load(src, fn)
        save(dst, fn, average(rs, keys.split(), vals.split()))
        if fn == "replication":
            save(
                dst,
                "unseen-fillers",
                average(
                    rs,
                    ["i", "domain", "arm", "copy"],
                    ["first", "second", "complete", "rank"],
                ),
            )
    pairs = []
    for fn, fields in [
        ("online", ["kind", "n", "arm", "copy"]),
        ("near-online", ["kind", "n", "arm", "copy"]),
        ("budget", ["domain", "n", "arm", "budget"]),
    ]:
        rows = load(src, fn)
        for r in rows:
            if "reference" in r:
                assert bool(int(r["ops"])) == (r["graph"] == r["reference"])
        sums = average(rows, fields, ["ops", "ept", "seconds"])
        by = groups(rows, fields)
        for out in sums:
            rs = by[tuple(out[k] for k in fields)]
            out["eps"] = sum(float(r["ops"]) for r in rs) / sum(
                float(r["seconds"]) for r in rs
            )
            out["wall_sd"] = stdev(float(r["seconds"]) for r in rs)
        save(dst, fn, sums)
        pfields = ["domain"] if fn == "budget" else ["kind"]
        for key, rs in groups(rows, pfields + ["n"]).items():
            comparison = defaultdict(dict)
            for r in rs:
                comparison[
                    r["seed"],
                    r["flip"],
                    r["block"],
                    r.get("copy", "0"),
                    r.get("budget", "32"),
                ][r["arm"]] = r
            for cp in ("0", "1"):
                for arm in ("joint-sparse", "mixed-sparse"):
                    ratios = []
                    for (_, _, _, copy, b), o in comparison.items():
                        if b != "32" or cp != copy or arm not in o:
                            continue
                        x, y = o["wide"], o[arm]
                        if int(x["ops"]) and x["graph"] == y["graph"]:
                            ratios.append(float(y["seconds"]) / float(x["seconds"]))
                    if ratios:
                        pairs.append(
                            dict(
                                study=fn,
                                domain=key[0],
                                n=key[1],
                                arm=arm,
                                copy=cp,
                                pairs=len(ratios),
                                ratio_median=median(ratios),
                                ratio_sd=stdev(ratios) if len(ratios) > 1 else "",
                            )
                        )
    save(dst, "same-graph", pairs)
    fresh = load(src, "fresh-online")
    result = []
    for (domain, arm), rs in groups(fresh, ["domain", "arm"]).items():
        assert all(bool(int(r["ops"])) == (r["graph"] == r["reference"]) for r in rs)
        ops = sum(int(r["ops"]) for r in rs)
        result.append(
            dict(
                domain=domain,
                arm=arm,
                worlds=len(rs),
                completed=ops,
                coverage=ops / len(rs),
                ept=ops / sum(int(r["paid"]) for r in rs),
                eps=ops / sum(float(r["seconds"]) for r in rs),
            )
        )
    save(dst, "fresh-online", result)
    for fn in ("cost", "updates", "mps-memory"):
        shutil.copyfile(src / (fn + ".csv"), dst / (fn + ".csv"))
    fit = load(src, "fit")
    if "mixed-sparse" not in {r["arm"] for r in fit}:
        fit += load(src, "extra-fit")
    save(dst, "fit", fit)
    save(
        dst,
        "weights",
        [
            dict(file=p.name, sha256=hashlib.sha256(p.read_bytes()).hexdigest())
            for p in sorted((src / "weights").glob("*.pt"))
        ],
    )
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(1, 3, figsize=(12, 3.8), constrained_layout=True)
    for n in (32, 256, 1024):
        curves = []
        for p in sorted((src / "pair-distributions").glob(f"*-{n}-*.npz")):
            with np.load(p) as z:
                tail = np.delete(z["kernel"][int(z["root"])], int(z["partner"]))
            curves.append(np.cumsum(np.sort(tail.astype(float))[::-1]) / tail.sum())
        y = np.mean(curves, axis=0)
        ax[0].plot(np.arange(1, len(y) + 1), y, label=str(n))
    ax[0].set(
        xscale="log",
        xlabel="Wrong partners, highest kernel first",
        ylabel="Share of total wrong kernel",
        title="Frozen wide kernel",
    )
    for m in ("wide", "positive", "field-sparse", "joint-sparse", "mixed-sparse"):
        r = sorted(
            [
                r
                for r in load(dst, "frozen")
                if r["side"] == "square"
                and r["kind"] == "two"
                and r["arm"] == m
                and r["copy"] == "0"
            ],
            key=lambda r: int(r["n"]),
        )
        ax[1].plot(
            [int(x["n"]) for x in r], [float(x["first"]) for x in r], ".-", label=m
        )
    ax[1].set(
        xscale="log",
        yscale="log",
        xlabel="Rows per role",
        ylabel="Correct first-parent probability",
        title="Nested distractors",
    )
    for arm in ("joint-sparse", "mixed-sparse"):
        r = sorted(
            [
                r
                for r in load(dst, "controls")
                if r["mode"] == "trained"
                and r["arm"] == arm
                and r["domain"] == "near"
                and r["res"] == "262144"
            ],
            key=lambda r: int(r["n"]),
        )
        for k, style in [("first", ".-"), ("complete", "x--")]:
            ax[2].plot(
                [int(x["n"]) for x in r],
                [float(x[k]) for x in r],
                style,
                label=arm + " " + k,
            )
    ax[2].set(
        xscale="log",
        yscale="log",
        xlabel="Rows per role",
        ylabel="Probability",
        title="One-field near misses",
    )
    for a in ax:
        a.grid(alpha=0.2)
        a.legend(fontsize=7)
    fig.savefig(dst / "selectivity.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main(*map(Path, sys.argv[1:]))
