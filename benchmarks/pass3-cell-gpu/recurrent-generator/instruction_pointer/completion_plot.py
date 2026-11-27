"""Plot macro recall, the same-type binding control, and held-target learning curves."""

import csv
import sys
from pathlib import Path
from statistics import mean
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def rows(path):
    with path.open() as f:
        return list(csv.DictReader(f))


def plot(d):
    free = rows(d / "free.csv")
    learning = rows(d / "learning.csv")
    sizes = [4, 8, 16, 32, 64, 128, 256, 1024]
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.1), layout="constrained")
    colors = {
        "factored": "#666666",
        "initial": "#b87612",
        "A": "#0072B2",
        "B": "#009E73",
        "C": "#CC6677",
    }
    for arm, color in colors.items():
        for axis, variant, budget in [(axes[0], None, 256), (axes[1], "pair", 16)]:
            yy = []
            for n in sizes:
                r = [
                    float(x["recall"])
                    for x in free
                    if x["arm"] == arm
                    and x["split"] == "matrix"
                    and int(x["size"]) == n
                    and int(x["slots"]) == budget
                    and (variant is None or x["variant"] == variant)
                ]
                yy.append(100 * mean(r))
            axis.plot(sizes, yy, "o-", ms=3, label=arm, color=color)
        if arm in "ABC":
            for seed in (9633, 5003, 1777):
                steps = []
                ces = []
                for stage in range(1, 9):
                    r = [
                        x
                        for x in learning
                        if x["arm"] == arm
                        and int(x["seed"]) == seed
                        and int(x["stage"]) == stage
                    ]
                    steps.append(int(r[0]["exposures"]))
                    ces.append(mean(float(x["held_ce"]) for x in r))
                axes[2].plot(
                    steps,
                    ces,
                    color=color,
                    alpha=0.5,
                    lw=1.5,
                    label=arm if seed == 9633 else None,
                )
    for ax, title in zip(
        axes[:2],
        ["Eight task families · 256 slots", "Same-type two-parent join · 16 slots"],
    ):
        ax.set(
            xscale="log",
            xticks=sizes,
            xticklabels=sizes,
            ylim=(-2, 102),
            title=title,
            xlabel="Visible Cells",
            ylabel="Distinct native target recall (%)",
        )
        ax.tick_params(axis="x", labelrotation=45)
    axes[2].set(
        title="Unseen instances · teacher forcing",
        xlabel="Complete target exposures",
        ylabel="Held token cross entropy (nats)",
    )
    for ax in axes:
        ax.legend(fontsize=8)
        ax.grid(alpha=0.2)
    fig.savefig(d / "learning.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    plot(Path(sys.argv[1]))
