"""Observed budget sweep for the frozen seed. Each dot is an independently terminated run."""

import argparse
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def plot(folder):
    with (folder / "frontier.csv").open() as f:
        rows = [r for r in csv.DictReader(f) if r["label"].startswith("pair")]
    colors = ("#232728", "#b55d13", "#3c7870", "#8263a2", "#3265b0")
    fig, axes = plt.subplots(2, 4, figsize=(13.5, 6), layout="constrained")
    for j, case in enumerate(("fact", "loopfact", "sum-divisors", "grammar-benefit-left-17119")):
        for i, metric in enumerate(("ept", "eps")):
            ax = axes[i, j]
            for mode, color, marker in zip("ABCDE", colors, ("o", "s", "^", "x", "+")):
                group = [r for r in rows if r["case"] == case and r["arm"] == mode]
                ax.scatter(
                    [100 * float(r["coverage"]) for r in group],
                    [float(r[metric]) for r in group],
                    color=color,
                    marker=marker,
                    label=mode,
                    s=28,
                    alpha=0.75,
                )
            if i == 0:
                ax.set_title(case.replace("grammar-benefit-left-17119", "Held grammar"))
            else:
                ax.set_xlabel("Reference facts covered (%)")
            if j == 0:
                ax.set_ylabel(
                    {"eps": "Effective operations / s", "ept": "Effective operations / paid request"}[metric]
                )
            ax.grid(alpha=0.2)
    axes[0, 0].legend(ncol=3, fontsize=8)
    fig.savefig(folder / "frontier.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("folder", type=Path)
    plot(p.parse_args().folder)
