# /// script
# requires-python = ">=3.10"
# dependencies = ["matplotlib>=3.8,<4"]
# ///
"""Measured recall on frozen states and native effects at matched request budgets."""

import csv
import sys
from pathlib import Path
from statistics import median

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

root = Path(sys.argv[1])
with (root / "frozen-curves.csv").open() as f:
    frozen = list(csv.DictReader(f))
with (root / "paid-curves.csv").open() as f:
    paid = list(csv.DictReader(f))
fig, axes = plt.subplots(1, 2, figsize=(10.2, 4.1), layout="constrained")
for arm, color, label in [
    ("prior", "#606060", "Prior DFM"),
    ("editor-full", "#2469a0", "Supervised, full Run"),
    ("flow-full", "#b04a30", "DFM, full Run"),
]:
    rr = [
        q
        for q in frozen
        if q["arm"] == arm and q["prompt"] == "free" and q["case"] == "sum-divisors"
    ]
    rr.sort(key=lambda q: int(q["page"]))
    axes[0].plot(
        [int(q["page"]) for q in rr],
        [100 * int(q["found_ops"]) / int(q["reference_ops"]) for q in rr],
        color=color,
        label=label,
        marker="o",
    )
    ss = [q for q in paid if q["arm"] == arm]
    budgets = sorted({int(q["budget"]) for q in ss})
    axes[1].plot(
        budgets,
        [median(int(q["ops"]) for q in ss if int(q["budget"]) == b) for b in budgets],
        color=color,
        label=label,
        marker="o",
    )
axes[0].set(
    title="Frozen native states, sum-divisors",
    xlabel="Generation pages",
    ylabel="Witnessed operation recall (%)",
)
axes[1].set(
    title="Independent native execution, sum-divisors",
    xlabel="Maximum paid requests",
    ylabel="Credited effective operations (median)",
)
for ax, ticks in zip(axes, ([1, 4, 16, 32], [1, 4, 16, 64, 256]), strict=True):
    ax.set_xscale("log")
    ax.set_xticks(ticks, [str(t) for t in ticks])
    ax.minorticks_off()
    ax.grid(axis="y", alpha=0.25)
    ax.legend(fontsize=8)
fig.savefig(root / "continuation-curves.png", dpi=165)
