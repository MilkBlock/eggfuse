# /// script
# requires-python = ">=3.10"
# dependencies = ["matplotlib>=3.8,<4"]
# ///
"""Verified frozen bindings and end-to-end native outcomes at measured budgets."""

import csv
import sys
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

root = Path(sys.argv[1])


def read(name):
    with (root / name).open() as f:
        return list(csv.DictReader(f))


frozen = read("frozen.csv")
native = read("native.csv")
fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.1), layout="constrained")
for arm, label in (
    ("independent", "Independent"),
    ("editor", "Supervised editor"),
    ("flow", "DFM"),
):
    hits = Counter()
    for r in frozen:
        if (
            r["arm"] == arm
            and r["case"] == "sum-divisors"
            and r["slots"] == "256"
            and r["steps"] == "1"
        ):
            hits[int(r["page"])] += int(r["hits"])
    (line,) = axes[0].plot([0, 1, 2], [0, hits[1], hits[2]], "o-", label=label)
    rows = [
        r
        for r in native
        if r["case"] == "sum-divisors"
        and r["arm"] == arm
        and r["block"] == "0"
        and r["pages"] == "2"
    ]
    axes[1].scatter(
        [int(r["paid"]) for r in rows],
        [100 * int(r["covered"]) / int(r["reference"]) for r in rows],
        color=line.get_color(),
        alpha=0.8,
        label=label,
    )
axes[0].set(
    xlabel="Pages generated per snapshot",
    ylabel="Different witnessed bindings recovered",
    title="Frozen states · 383 known bindings",
    xticks=[0, 1, 2],
)
axes[1].set(
    xlabel="Paid CCP requests",
    ylabel="Derived reference facts covered (%)",
    title="Independent execution · 8,018 reference facts",
    xscale="symlog",
)
for a in axes:
    a.grid(alpha=0.2)
    a.legend(fontsize=8)
fig.savefig(root / "sum-divisors.png", dpi=160)
