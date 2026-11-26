"""Actual reference facts recovered at acknowledged publications by cold wall time."""

import csv
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent
with (root / "clock.csv").open() as src:
    results = list(csv.DictReader(src))
fig, axes = plt.subplots(1, 3, figsize=(11, 3.4), constrained_layout=True)
for case, ax in zip(("fact", "loopfact", "sum-divisors"), axes):
    for method, title in (
        ("factored", "Factorized random"),
        ("initial", "Frozen initial"),
        ("full-A", "A · whole token"),
        ("full-E", "E · scoped credit"),
    ):
        buckets = defaultdict(list)
        for r in results:
            if r["case"] == case and r["arm"] == method and r["block"] == "0":
                buckets[float(r["seconds"])].append(
                    100 * int(r["facts"]) / int(r["reference"])
                )
        times = sorted(t for t in buckets if t <= 64)
        ax.plot(times, [mean(buckets[t]) for t in times], marker=".", label=title)
    ax.set(
        xscale="log",
        xlabel="Cold wall time (s)",
        title=case,
        ylabel="Reference facts (%)",
    )
    ax.set_xticks([0.5, 2, 8, 32], ["0.5", "2", "8", "32"])
    ax.grid(True, alpha=0.2)
axes[-1].legend(fontsize=7, loc="lower right")
fig.savefig(root / "coverage-time.png", dpi=150)
