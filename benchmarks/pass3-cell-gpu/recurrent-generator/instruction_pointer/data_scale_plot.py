# /// script
# requires-python = ">=3.10"
# dependencies = ["matplotlib>=3.8,<4"]
# ///
"""Plot actual paired native outcomes and held-out branch accuracy from collected records."""

import csv
import json
import sys
from pathlib import Path
from statistics import median

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

root = Path(sys.argv[1])
held = json.loads((root / "held-metrics.json").read_text())
with (root / "pairs.csv").open() as f:
    runs = list(csv.DictReader(f))
levels = [10000, 100000, 1000000]
fig, axes = plt.subplots(1, 3, figsize=(11, 3.7), layout="constrained")
for size, color in (("100K", "#21618c"), ("1M", "#b2461c")):
    for full, style in ((True, "-"), (False, "--")):
        for metric, ax in zip(
            ("port_accuracy", "fact", "sum-divisors"), axes, strict=True
        ):
            ys = []
            for n in levels:
                if metric == "port_accuracy":
                    values = [
                        100 * r[metric]
                        for r in held
                        if r["budget"] == ("complete" if full else "fixed1568")
                        and r["n"] == n
                        and r["size"] == size
                    ]
                else:
                    values = [
                        100 * int(r["facts"]) / int(r["ref"])
                        for r in runs
                        if r["budget"] == ("passes" if full else "iso1568")
                        and r["case"] == metric
                        and r["backend"] == "legacy-cpu"
                        and r["size"] == size
                        and r["dataset"] == f"n{n}"
                    ]
                assert len(values) == 3
                ys.append(median(values))
            ax.plot(
                levels,
                ys,
                linestyle=style,
                marker="o",
                ms=3,
                color=color,
                label=f"{size}, " + ("4+ passes" if full else "1,568 updates"),
            )
for ax, title in zip(
    axes,
    (
        "Held-out parent branch accuracy",
        "Independent fact Coverage",
        "Independent sum-divisors Coverage",
    ),
    strict=True,
):
    ax.set(xscale="log", title=title, xlabel="Training plans", ylabel="Percent")
    ax.set_xticks(levels, ["10K", "100K", "1M"])
    ax.minorticks_off()
    ax.grid(axis="y", alpha=0.25)
axes[0].legend(fontsize=8)
fig.savefig(root / "learning-curves.png", dpi=160)
