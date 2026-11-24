"""Compare independent rollouts at their actual sealed Run boundaries."""

import csv
import json
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt


def plot(dest):
    plt.rcParams.update({"svg.hashsalt": "eggfuse-guard", "svg.fonttype": "none"})
    curves = defaultdict(list)
    with (dest / "runs.csv").open() as f:
        for row in csv.DictReader(f):
            curves[row["case"], row["policy"]].append(row)
    results = json.loads((dest / "results.json").read_text())
    focus = ("control", "joint-balanced", "s8", "p8", "p8-delta")
    cases = ("cyk801", "grammar-4691132", "sum-divisors", "jacobi")
    fig, axes = plt.subplots(4, 4, figsize=(14, 10), layout="constrained")
    for i, case in enumerate(cases):
        for j, axis in enumerate(("seconds", "paid", "scored_and_interfaces", "eps")):
            ax = axes[i, j]
            for arm in focus:
                rows = curves[case, arm]
                if axis == "eps":
                    r = next(
                        x for x in results if x["case"] == case and x["policy"] == arm
                    )
                    ax.scatter(r["eps"], 100 * r["derived"] / r["reference"], label=arm)
                else:
                    ax.step(
                        [float(r[axis]) for r in rows],
                        [100 * int(r["derived"]) / int(r["reference"]) for r in rows],
                        where="post",
                        label=arm,
                    )
            ax.set_xscale("symlog", linthresh=(0.01, 10, 100, 10)[j])
            if i == 0:
                ax.set_title(
                    (
                        "Online seconds",
                        "Paid requests",
                        "Scored positions + interface reads",
                        "Signed operations per second",
                    )[j]
                )
            if j == 0:
                ax.set_ylabel(case + "\nCoverage (%)")
            ax.grid(alpha=0.2)
    fig.legend(
        *axes[0, 0].get_legend_handles_labels(),
        loc="outside upper center",
        ncol=len(focus),
    )
    fig.savefig(dest / "coverage.svg", metadata={"Date": None})
    plt.close(fig)
    svg = dest / "coverage.svg"
    svg.write_text("\n".join(line.rstrip() for line in svg.read_text().splitlines()) + "\n")


if __name__ == "__main__":
    plot(Path(__file__).parent / "run-recall" / "guard-study")
