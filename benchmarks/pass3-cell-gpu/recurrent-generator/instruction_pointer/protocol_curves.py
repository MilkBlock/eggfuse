"""Plot the measured prefix cost at shared reference-fact coverage thresholds."""

import argparse
import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def plot(dest, cases):
    fig, axes = plt.subplots(
        len(cases),
        3,
        figsize=(11, 2.3 * len(cases)),
        squeeze=False,
        layout="constrained",
    )
    records = []
    for axs, case in zip(axes, cases, strict=True):
        info = json.loads((dest / (case + ".json")).read_bytes())
        curves = info["cost_curve"]
        common = min(max(p["derived"] for p in pts) for pts in curves.values())
        targets = np.unique(np.linspace(1, common, min(100, common), dtype=int))
        for arm, pts in curves.items():
            crosses = [next(p for p in pts if p["derived"] >= n) for n in targets]
            for n, p in zip(targets, crosses, strict=True):
                records.append(dict(case=case, arm=arm, target=int(n), **p))
            for ax, key in zip(axs, ("tokens", "visits", "elapsed"), strict=True):
                ax.step(
                    targets * 100 / info["reference"],
                    [p[key] for p in crosses],
                    where="pre",
                    label=arm,
                )
                ax.grid(alpha=0.18)
        axs[0].set_ylabel(case.replace("grammar-stride", "stride-") + "\nCost")
        for ax in axs:
            ax.tick_params(labelsize=8)
    for ax, title in zip(
        axes[0],
        ["Requests + neural controls", "Candidate visits", "Inclusive seconds"],
        strict=True,
    ):
        ax.set_title(title)
    for ax in axes[-1]:
        ax.set_xlabel("Reference derived facts reached (%)")
    axes[0, 0].legend(ncol=4, fontsize=8)
    fig.savefig(dest / "matched-coverage.pdf")
    plt.close(fig)
    with (dest / "matched-coverage.csv").open("w") as out:
        w = csv.DictWriter(out, fieldnames=records[0].keys(), lineterminator="\n")
        w.writeheader()
        w.writerows(records)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("dest", type=Path)
    ap.add_argument("cases", nargs="+")
    a = ap.parse_args()
    plot(a.dest, a.cases)
