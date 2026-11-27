"""Render reproducible cost/coverage plots from the paired native measurements."""

import argparse
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def plot(report):
    with (report / "paired.csv").open() as src:
        rows = list(csv.DictReader(src))
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.8), constrained_layout=True)
    for series, mode, title in [
        ("clean", "prim", "Primitive stream"),
        ("clean", "flat", "Higher + stream"),
        ("singleclean", "flat", "Entry-only Higher"),
    ]:
        group = [
            r
            for r in rows
            if r["case"].startswith("scale-fork-")
            and r["case"].endswith("-1-17")
            and r["series"] == series
            and r["mode"] == mode
            and r["method"] == "empty"
        ]
        group.sort(key=lambda r: int(r["reference"]))
        for ax, metric in zip(axes, ["ept", "eps"]):
            xs = [int(r["reference"]) for r in group if r["exact_endpoint"] == "True"]
            ys = [float(r[metric]) for r in group if r["exact_endpoint"] == "True"]
            ax.plot(xs, ys, "o-", label=title)
            ax.set_xscale("log", base=2)
            ax.set_xticks([6, 16, 32, 64, 128, 256, 512], labels=["6", "16", "32", "64", "128", "256", "512"])
            ax.set_xlabel("Primitive operations in the critical-path job")
            ax.set_ylabel(metric.upper())
            ax.grid(True, alpha=0.2)
    axes[0].legend(fontsize=8)
    fig.suptitle("Matched full terminal graphs · four-step Edit Flow")
    fig.savefig(report / "matched-scaling.png", dpi=160)
    plt.close(fig)
    with (report / "natural-frontier.csv").open() as f:
        points = list(csv.DictReader(f))
    fig, axes = plt.subplots(2, 2, figsize=(10, 6), constrained_layout=True)
    for ax, case in zip(axes.flat, ["fact", "loopfact", "sum-divisors", "grammar-benefit-left-17119"]):
        for mode, marker in [("prim", "o"), ("small", "^"), ("flat", "s"), ("wide", "x")]:
            group = [r for r in points if r["case"] == case and r["mode"] == mode]
            ax.scatter(
                [100 * float(r["coverage"]) for r in group],
                [float(r["ept"]) for r in group],
                s=[13 + float(r["eps"]) / 6 for r in group],
                marker=marker,
                alpha=0.63,
                label=mode,
            )
        ax.set_title(case)
        ax.set_xlabel("Reference facts covered (%)")
        ax.set_ylabel("EPT")
        ax.grid(True, alpha=0.2)
    axes[0, 0].legend(ncol=2, fontsize=8)
    fig.suptitle(
        "Independent execution · both decoders, 1/2/4/8 pages per Run · marker area increases with EPS"
    )
    fig.savefig(report / "natural-frontier.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("report", type=Path)
    plot(p.parse_args().report)
