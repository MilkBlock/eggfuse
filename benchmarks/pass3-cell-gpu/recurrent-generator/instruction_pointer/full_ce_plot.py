"""Standalone learning and paid-budget curves from the finished native measurements."""

import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

matplotlib.rcParams["svg.hashsalt"] = "cell-complete-pretraining"

REPORT = Path(__file__).resolve().parent / "run-recall/full-ce-scaling"


def rows(name):
    with (REPORT / name).open() as f:
        return list(csv.DictReader(f))


def plot():
    matrix = rows("matrix.csv")
    native = rows("native.csv")
    labels = ["local", "center", "layer01", "layer03"]
    locked = [
        r["model"]
        for r in native
        if r["phase"] == "outer" and r["model"] not in ("sweep", "initial")
    ]
    labels.extend(
        n for n in sorted({x.rsplit("-s", 1)[0] for x in locked}) if n not in labels
    )
    fig, (fit, learn, paid) = plt.subplots(
        1, 3, figsize=(13, 4.1), layout="constrained"
    )
    for name in labels:
        points = defaultdict(list)
        for r in matrix:
            if r["name"] == name:
                points[int(r["exposures"])].append(r)
        if not points:
            continue
        xs = sorted(points)
        for ax, key, scale in (
            (fit, "validation_ce", 1),
            (learn, "inner_loopfact", 100),
        ):
            values = [[float(r[key]) * scale for r in points[x]] for x in xs]
            ys = [mean(v) for v in values]
            (line,) = ax.plot(xs, ys, "o-", ms=4, label=name)
            ax.vlines(
                xs,
                [min(v) for v in values],
                [max(v) for v in values],
                color=line.get_color(),
                lw=2,
            )
    for ax in (fit, learn):
        ax.set_xscale("log")
        ax.set_xlabel("Complete-token exposures per fit")
    fit.set_ylabel("Validation complete-token CE")
    learn.set_ylabel("loopfact budget-averaged coverage (%)")
    fit.legend(fontsize=8)
    outer = [r for r in native if r["phase"] == "outer"]
    if outer:
        curves = defaultdict(lambda: defaultdict(list))
        for r in outer:
            label = r["model"].rsplit("-s", 1)[0]
            curves[label][int(r["budget"])].append(100 * float(r["coverage"]))
        for r in rows("baselines.csv"):
            if r["case"] == "sum-divisors" and r["arm"] in ("random", "history"):
                curves[r["arm"]][int(r["cap"])].append(100 * float(r["coverage"]))
        for label, ps in curves.items():
            xs = sorted(ps)
            paid.plot(xs, [mean(ps[x]) for x in xs], "o-", ms=4, label=label)
        paid.legend(fontsize=8)
    else:
        paid.text(
            0.5,
            0.5,
            "Awaiting locked outer evaluation",
            ha="center",
            transform=paid.transAxes,
        )
    paid.set_xlabel("Paid-request budget")
    paid.set_ylabel("sum-divisors coverage (%)")
    for ax in (fit, learn, paid):
        ax.grid(alpha=0.22)
    fig.savefig(REPORT / "learning-curves.svg", metadata={"Date": None})
    plt.close(fig)


if __name__ == "__main__":
    plot()
