"""Plot equal-budget nested fits and native same-clock performance; no fitting or interpolation."""

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean

import matplotlib.pyplot as plt


def rows(path):
    with path.open() as stream:
        return list(csv.DictReader(stream))


def plot(folder):
    family = {r["arm"]: float(r["coverage"]) for r in rows(folder / "held-dags.csv")}
    native = {
        (r["case"], r["arm"]): float(r["Coverage"]) for r in rows(folder / "native.csv")
    }
    clock = defaultdict(list)
    for r in rows(folder / "clock.csv"):
        if r["seed"] == "9633" and r["case"] == "sum-divisors":
            clock[r["arm"], float(r["seconds"])].append(int(r["effective"]))
    fig, ax = plt.subplots(1, 3, figsize=(11, 3.4), constrained_layout=True)
    for axis, lookup, title in (
        (ax[0], family, "Held-out relation DAGs"),
        (
            ax[1],
            {arm: v for (case, arm), v in native.items() if case == "sum-divisors"},
            "EggCC sum-divisors",
        ),
    ):
        for u, color in [(192, "#296b9c"), (1216, "#ab4525")]:
            axis.plot(
                [16, 64, 152],
                [100 * lookup[f"omission-n{n}-u{u}"] for n in (16, 64, 152)],
                marker="o",
                color=color,
                label=f"{u:,} updates",
            )
        axis.axhline(
            100 * lookup["factored"],
            color="#5b5a5b",
            ls="--",
            label="Factorized random",
        )
        axis.set(
            xticks=[16, 64, 152],
            xlabel="Training programs",
            ylabel="Final coverage (%)",
            title=title,
        )
        axis.legend(fontsize=7)
    for arm, label in (
        ("initial", "Initial"),
        ("factored", "Factorized random"),
        ("mixed-n480-u1920", "480 programs, 1,920 updates"),
    ):
        times = sorted(t for a, t in clock if a == arm and t <= 16)
        ax[2].step(
            times, [mean(clock[arm, t]) for t in times], where="post", label=label
        )
    ax[2].set(
        xscale="log",
        xlabel="Cold wall time (s)",
        ylabel="Confirmed effective operations",
        title="EggCC sum-divisors",
    )
    ax[2].legend(fontsize=7)
    for axis in ax:
        axis.grid(axis="y", alpha=0.25)
    fig.savefig(folder / "learning-curves.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    plot(parser.parse_args().folder)
