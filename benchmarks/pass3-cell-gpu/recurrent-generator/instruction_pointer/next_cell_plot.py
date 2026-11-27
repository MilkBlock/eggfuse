"""Plot measured epochs and seed spread for the pretraining corpus."""

import argparse
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def plot(folder):
    with (folder / "learning.csv").open() as f:
        rows = list(csv.DictReader(f))
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.3), constrained_layout=True)
    for arm, label, color in [
        ("ce24", "24 programs", "#007696"),
        ("ce200", "200 programs", "#782f76"),
        ("ce200mixed", "200 + mixed tapes", "#d26b13"),
    ]:
        for seed in ("9633", "5003"):
            values = [r for r in rows if r["arm"] == arm and r["seed"] == seed]
            for axis, metric, name in zip(
                axes,
                ["train_ce", "held_ce", "held_expected_recall64"],
                [
                    "Training CE (nats / Cell)",
                    "Held-out CE (nats / Cell)",
                    "Known-target recall at 64 slots (%)",
                ],
            ):
                seen = [r for r in values if r[metric]]
                axis.plot(
                    [int(r["exposures"]) / 1e6 for r in seen],
                    [
                        float(r[metric])
                        * (100 if metric.startswith("held_expected") else 1)
                        for r in seen
                    ],
                    marker=".",
                    color=color,
                    linestyle="-" if seed == "9633" else "--",
                    lw=1.4,
                    label=label if seed == "9633" else None,
                )
                axis.set(xlabel="Complete target exposures (millions)", ylabel=name)
                axis.grid(alpha=0.2)
    axes[0].legend(frameon=False, fontsize=8)
    fig.savefig(folder / "learning.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    plot(parser.parse_args().folder)
