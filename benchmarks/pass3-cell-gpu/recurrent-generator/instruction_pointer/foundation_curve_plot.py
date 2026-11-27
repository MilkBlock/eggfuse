"""Plot measured CE and native coverage; retain zero-exposure checkpoints."""

import csv
import sys
from pathlib import Path

import matplotlib.pyplot as plt


def plot(out):
    with (out / "learning.csv").open() as f:
        data = list(csv.DictReader(f))
    fig, axes = plt.subplots(1, 3, figsize=(13, 4), layout="constrained")
    for col, field in enumerate(("held", "coverage", "coverage")):
        ax = axes[col]
        attrs = (
            [("multi", n) for n in (4, 12, 24, 48)]
            if col < 2
            else [
                (c, 12)
                for c in (
                    "primitive",
                    "half",
                    "short",
                    "medium-half",
                    "medium",
                    "multi",
                )
            ]
        )
        for cat, size in attrs:
            rows = sorted(
                (
                    r
                    for r in data
                    if (r["cat"], int(r["size"]), r["width"], r["fresh"])
                    == (cat, size, "32", "False")
                ),
                key=lambda r: int(r["samples"]),
            )
            label = (rows[0]["states"].split(".")[0] + " states") if col < 2 else cat
            ax.plot(
                [int(r["samples"]) for r in rows],
                [float(r[field]) * (100 if col else 1) for r in rows],
                marker="o",
                ms=4,
                label=label,
            )
        ax.set(
            xscale="symlog",
            xlabel="Complete Token exposures",
            ylabel="Held-out CE" if not col else "Native coverage (%)",
        )
        ax.set_xscale("symlog", linthresh=512)
        ticks = [0, 512, 2048, 8192] + ([32768] if col < 2 else [])
        ax.set_xticks(ticks, ["0", "512", "2k", "8k"] + (["32k"] if col < 2 else []))
        ax.set_title(
            (
                "Fit on verified targets",
                "Independent execution",
                "Abstraction at 72 states",
            )[col]
        )
        ax.grid(alpha=0.2)
        ax.legend(fontsize=8)
    fig.savefig(out / "learning.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    plot(Path(sys.argv[1]))
