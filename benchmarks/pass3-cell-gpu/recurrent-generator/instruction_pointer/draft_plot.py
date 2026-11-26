# /// script
# requires-python = ">=3.10"
# dependencies = ["matplotlib>=3.8,<4"]
# ///
"""Measured settled native operations at actual Run boundaries, plus binding-set recall."""

import csv
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

root = Path(sys.argv[1])


def rows(name):
    with (root / name).open() as f:
        return list(csv.DictReader(f))


points = rows("curves.csv")
recall = rows("recall.csv")
fig, axes = plt.subplots(1, 3, figsize=(12.8, 3.8), layout="constrained")
for arm, label in [
    ("fifo", "FIFO"),
    ("set", "Selected set"),
    ("relative", "Relative selection"),
    ("page", "Per page"),
    ("page-multi", "Per page + set training"),
]:
    group = [
        r
        for r in points
        if (r["track"], r["case"], r["device"], r["arm"])
        == ("paired", "sum-divisors", "cpu", arm)
    ]
    for ax, key, title in zip(
        axes[:2],
        ["policy_seconds", "online_wall"],
        ["Sampling + selection (s)", "End-to-end time (s)"],
        strict=True,
    ):
        ax.step(
            [float(r[key]) for r in group],
            [int(r["settled_ops"]) for r in group],
            where="post",
            label=label,
        )
        ax.set(xlabel=title, ylabel="Settled effective operations")
        ax.grid(alpha=0.25)
axes[0].set_title("sum-divisors · CPU")
axes[1].set_title("Same native executions")
axes[0].legend(fontsize=7)
for arm in ("frozen", "single", "multi"):
    group = [r for r in recall if r["arm"] == arm]
    budgets = sorted({int(r["draws"]) for r in group})
    y = [
        100
        * sum(int(r["distinct_hits"]) for r in group if int(r["draws"]) == n)
        / sum(int(r["verified"]) for r in group if int(r["draws"]) == n)
        for n in budgets
    ]
    axes[2].plot(budgets, y, marker=".", label=arm)
axes[2].set(
    xlabel="Address draws per frozen state",
    ylabel="Distinct verified binding recall (%)",
    title="Four held-out workloads",
    xscale="log",
)
axes[2].legend(fontsize=8)
axes[2].grid(alpha=0.25)
fig.savefig(root / "curves.png", dpi=170)
