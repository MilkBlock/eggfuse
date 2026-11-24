"""Plot exclusive native semantic coverage against measured elapsed time."""

import csv
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt


def plot(path):
    traces = defaultdict(list)
    with (path / "runs.csv").open() as stream:
        for row in csv.DictReader(stream):
            traces[row["case"], row["arm"]].append(
                (
                    float(row["elapsed"]),
                    100 * int(row["derived"]) / int(row["denominator"]),
                )
            )
    cases = list(dict.fromkeys(c for c, _ in traces))
    arms = {
        "legacy": "Previous two-owner",
        "two": "Matched two-owner",
        "free": "Recursive",
        "pending": "Recursive + pending",
    }
    fig, axes = plt.subplots(3, 3, figsize=(13, 8), layout="constrained")
    for ax, case in zip(axes.flat, cases, strict=True):
        for arm, label in arms.items():
            points = [(0, 0), *traces[case, arm]]
            x, y = zip(*points)
            (line,) = ax.step(x, y, where="post", label=label, lw=1.4)
            ax.plot(x[-1], y[-1], ".", color=line.get_color())
        ax.set_title(case, fontsize=10)
        ax.set_xlim(left=0)
        ax.set_ylim(bottom=0)
        ax.grid(alpha=0.2)
    fig.supxlabel("Elapsed seconds of exclusive execution")
    fig.supylabel("Reference derived final rows covered (%)")
    fig.legend(
        *axes.flat[0].get_legend_handles_labels(), loc="outside upper center", ncol=4
    )
    fig.savefig(path / "coverage.svg", metadata={"Date": None})
    plt.close(fig)


if __name__ == "__main__":
    plot(Path(__file__).parent / "run-recall" / "recursive-agent")
