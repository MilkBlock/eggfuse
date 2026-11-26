"""Draw the measured five-seed cumulative discovery curves from the published CSV."""

import csv
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def plot(folder):
    with (folder / "curves.csv").open() as f:
        rows = list(csv.DictReader(f))
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.6))
    arms = [
        ("uniform", "Uniform tokens"),
        ("unique", "Without replacement"),
        ("factored", "Uniform template then refs"),
        ("A", "Frozen A"),
        ("D", "Frozen D"),
        ("oracle", "Offline oracle"),
    ]
    for ax, src, label in zip(
        axes, ("teacher", "rollout"), ("Teacher states (109)", "Model states (76)")
    ):
        for i, (arm, name) in enumerate(arms):
            seq = [r for r in rows if r["source"] == src and r["arm"] == arm]
            ax.plot(
                [int(r["budget"]) for r in seq],
                [float(r["productive"]) for r in seq],
                linestyle="--" if arm == "oracle" else "-",
                marker=["o", "x", "s", "+", "^", "."][i],
                label=name,
            )
        ax.set(
            xscale="log",
            yscale="log",
            title=label,
            xlabel="Complete tokens per state, capped by domain",
        )
        ax.set_xticks([4, 16, 64, 256], labels=["4", "16", "64", "256"])
        ax.grid(alpha=0.2, which="major")
    axes[0].set_ylabel("Distinct productive bindings, summed across states")
    fig.legend(
        *axes[0].get_legend_handles_labels(), loc="lower center", ncol=3, frameon=False
    )
    fig.tight_layout(rect=(0, 0.14, 1, 1))
    fig.savefig(folder / "discovery.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    plot(Path(sys.argv[1]))
