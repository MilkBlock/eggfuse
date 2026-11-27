"""Plot conditional selection and free full-token mass on the same native worlds."""

import csv
import sys
from pathlib import Path
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def plot(d):
    with (d / "equality.csv").open() as f:
        rows = list(csv.DictReader(f))
    fig, axes = plt.subplots(1, 2, figsize=(9.2, 3.8), constrained_layout=True)
    for arm, label, color in [
        ("B", "B  tree", "#7f7170"),
        ("flat", "Dense row", "#aa7833"),
        ("C", "C  fields", "#427ca7"),
        ("D", "D  fields + identity", "#237757"),
    ]:
        data = [r for r in rows if r["arm"] == arm]
        for ax, key in zip(axes, ["second", "full"]):
            ax.plot(
                [int(r["size"]) for r in data],
                [100 * float(r[key]) for r in data],
                marker="o",
                ms=3,
                label=label,
                color=color,
            )
    for ax, title in zip(
        axes,
        [
            "Correct second parent | correct prefix",
            "Effective complete token | empty prefix",
        ],
    ):
        ax.set_xscale("log", base=2)
        ax.set_xlabel("Same-type visible cells")
        ax.set_ylabel("Probability (%)")
        ax.grid(alpha=0.22)
        ax.set_title(title, fontsize=10)
    axes[1].set_yscale("log")
    axes[1].legend(fontsize=8)
    fig.savefig(d / "binding-curves.png", dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    plot(Path(sys.argv[1]))
