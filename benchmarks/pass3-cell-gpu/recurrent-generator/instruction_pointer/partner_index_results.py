"""Publish reproducible aggregate diagnostics and paired wall-clock comparisons."""

import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean, median, stdev
import shutil
import sys


def load(d, name):
    with (d / (name + ".csv")).open() as f:
        return list(csv.DictReader(f))


def save(d, name, rows):
    with (d / (name + ".csv")).open("w") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def groups(rows, keys):
    g = defaultdict(list)
    for r in rows:
        g[tuple(r[k] for k in keys)].append(r)
    return g


def summary(rows, keys, values):
    result = []
    for key, rs in sorted(groups(rows, keys).items()):
        out = dict(zip(keys, key), trials=len(rs))
        for v in values:
            nums = [float(r[v]) for r in rs if r[v] != ""]
            out[v] = mean(nums) if nums else ""
        result.append(out)
    return result


def report(src, dst):
    dst.mkdir(parents=True, exist_ok=True)
    for name, keys, values in [
        (
            "frozen",
            "mode n arm",
            "root additive_root second complete empirical distinct_reads colliding_wrong wrong_mass true_mass max_wrong tv_scan refinement_fallback distinct_valid",
        ),
        (
            "dense",
            "n arm",
            "hits ops root_rank wrong_max_k true_max_k winning_wrong_heads wrong_partners_in_all_heads",
        ),
        ("trees", "kind arm", "ops paid seconds"),
        ("shared-snapshot", "mode n", "first second complete mean_distinct_reads"),
        ("prefixes", "arm paid", "ops"),
    ]:
        rs = load(src, name)
        save(dst, name, summary(rs, keys.split(), values.split()))
        if name == "frozen":
            assert len(rs) == 624
            save(
                dst,
                "seed-probability",
                summary(
                    rs,
                    ["mode", "n", "seed", "arm"],
                    ["root", "second", "complete", "empirical"],
                ),
            )
    rs = load(src, "online")
    assert len(rs) == 354 and all(
        (r["graph"] == r["reference"]) == (float(r["coverage"]) == 1) for r in rs
    )
    for file, rows in [
        ("online", rs),
        (
            "multi-curve",
            [
                r
                for r in rs
                if r["mode"] == "multi"
                and r["block"] == "0"
                and (r["n"] != "32768" or r["i"] == "511000")
            ],
        ),
    ]:
        out = []
        for key, rr in sorted(groups(rows, ["mode", "n", "paid", "arm"]).items()):
            ops = sum(int(r["ops"]) for r in rr)
            out.append(
                dict(
                    mode=key[0],
                    n=key[1],
                    paid=key[2],
                    arm=key[3],
                    trials=len(rr),
                    full=sum(r["graph"] == r["reference"] for r in rr),
                    coverage=mean(float(r["coverage"]) for r in rr),
                    ept=ops / sum(int(r["paid"]) for r in rr),
                    eps=ops / sum(float(r["seconds"]) for r in rr),
                    median_wall=median(float(r["seconds"]) for r in rr),
                )
            )
        save(dst, file, out)
    shared = load(src, "shared-online")
    by = groups(shared, ["mode", "n", "paid", "arm"])
    ss = []
    for key, rr in sorted(by.items()):
        op = sum(int(r["ops"]) for r in rr)
        ss.append(
            dict(
                mode=key[0],
                n=key[1],
                paid=key[2],
                arm=key[3],
                trials=len(rr),
                coverage=mean(float(r["coverage"]) for r in rr),
                ept=op / sum(int(r["paid"]) for r in rr),
                eps=op / sum(float(r["seconds"]) for r in rr),
            )
        )
    save(dst, "shared-online", ss)
    pairs = defaultdict(list)
    for key, rr in groups(
        rs, ["mode", "n", "paid", "seed", "i", "flip", "block"]
    ).items():
        arms = {r["arm"]: r for r in rr}
        base = arms["legacy"]
        for arm in ["linear", "refined"]:
            r = arms[arm]
            if base["graph"] == r["graph"] and float(r["coverage"]) > 0:
                pairs[(*key[:3], arm)].append(
                    float(r["seconds"]) / float(base["seconds"])
                )
    save(
        dst,
        "paired",
        [
            dict(
                mode=k[0],
                n=k[1],
                paid=k[2],
                arm=k[3],
                pairs=len(v),
                wall_ratio=median(v),
                sd=stdev(v) if len(v) > 1 else "",
            )
            for k, v in sorted(pairs.items())
        ],
    )
    for n in ["cost", "updates"]:
        shutil.copyfile(src / (n + ".csv"), dst / (n + ".csv"))
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 3, figsize=(12, 3.6), constrained_layout=True)
    for arm in ["legacy", "linear", "refined"]:
        frozen = sorted(
            [r for r in load(dst, "frozen") if r["arm"] == arm and r["mode"] == "hard"],
            key=lambda r: int(r["n"]),
        )
        axes[0].plot(
            [int(r["n"]) for r in frozen],
            [100 * float(r["second"]) for r in frozen],
            "o-",
            label=arm,
        )
        curve = sorted(
            [
                r
                for r in load(dst, "multi-curve")
                if r["arm"] == arm and r["n"] == "32768"
            ],
            key=lambda r: int(r["paid"]),
        )
        axes[1].plot(
            [int(r["paid"]) for r in curve],
            [float(r["coverage"]) * 8 for r in curve],
            "o-",
            label=arm,
        )
        perf = sorted(
            [r for r in load(dst, "cost") if r["arm"] == arm], key=lambda r: int(r["n"])
        )
        axes[2].plot(
            [int(r["n"]) for r in perf],
            [float(r["page_ms"]) for r in perf],
            "o-",
            label=arm,
        )
    axes[0].set(
        xlabel="Rows / role", ylabel="Conditional partner probability (%)", xscale="log"
    )
    axes[1].set(
        xlabel="Paid requests",
        ylabel="Distinct native effects (out of 8)",
        xscale="log",
    )
    axes[2].set(
        xlabel="Rows / role",
        ylabel="32-slot GPU forward (ms)",
        xscale="log",
        yscale="log",
    )
    for ax in axes:
        ax.grid(alpha=0.25)
        ax.legend(fontsize=8)
    fig.savefig(dst / "partner-addressing.png", dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    report(*map(Path, sys.argv[1:]))
