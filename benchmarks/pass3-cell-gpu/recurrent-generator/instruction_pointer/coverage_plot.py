"""Paired advantage over factored random; bands span the three trained checkpoints."""

import csv
import sys
from collections import Counter
from pathlib import Path
from statistics import mean

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def plot(dest):
    values = Counter()
    with (dest / "frozen-seeds.csv").open() as f:
        for row in csv.DictReader(f):
            values[
                row["source"], row["arm"], int(row["fit_seed"]), int(row["budget"])
            ] += int(row["matched_productive"]) / 5
    budgets = (4, 16, 64, 256)
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.8), sharey=True)
    for source, title, ax in zip(
        ("teacher", "rollout"), ("Teacher states (109)", "Autonomous states (76)"), axes
    ):
        ax.axhline(0, color="black", lw=1, ls="--", label="Factored random")
        for arm, label in (
            ("original", "Original loss"),
            ("coverage", "Coverage loss"),
            ("failure", "Coverage + failure supervision"),
        ):
            diffs = [
                [
                    values[source, arm, s, b] - values[source, "factored", 0, b]
                    for s in (9633, 5003, 1777)
                ]
                for b in budgets
            ]
            (line,) = ax.plot(budgets, list(map(mean, diffs)), marker="o", label=label)
            ax.fill_between(
                budgets,
                list(map(min, diffs)),
                list(map(max, diffs)),
                alpha=0.13,
                color=line.get_color(),
            )
        ax.set_xscale("log", base=2)
        ax.set_xticks(budgets, labels=[str(x) for x in budgets])
        ax.set(title=title, xlabel="Complete-token budget per state")
        ax.grid(axis="y", alpha=0.2)
    axes[0].set_ylabel("Additional distinct productive computations")
    fig.legend(
        *axes[0].get_legend_handles_labels(), loc="lower center", ncol=2, frameon=False
    )
    fig.tight_layout(rect=(0, 0.17, 1, 1))
    fig.savefig(dest / "frontier.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    plot(Path(sys.argv[1]))
