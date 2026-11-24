"""Coverage over paid requests, counted visits and native elapsed time."""

import csv
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt


def plot(dest):
    plt.rcParams.update({"svg.hashsalt": "eggfuse-cell-stream", "svg.fonttype": "none"})
    data = defaultdict(list)
    for src in (dest / "runs.csv", dest / "extended" / "runs.csv"):
        if not src.exists():
            continue
        with src.open() as f:
            for row in csv.DictReader(f):
                arm = row["arm"] if src.parent == dest else "stream (extended)"
                data[row["case"], arm].append(row)
    cases = list(dict.fromkeys(c for c, _ in data))
    for i, (axis, label) in enumerate(
        [
            ("elapsed", "Online wall time (s)"),
            ("paid", "Paid tokens"),
            ("visits", "Candidate and interface visits"),
        ]
    ):
        fig, axes = plt.subplots(
            3, 3, figsize=(13, 8), layout="constrained", sharey=True
        )
        for ax, c in zip(axes.flat, cases, strict=True):
            for arm in ("fixed", "dynamic", "dense", "stream", "stream (extended)"):
                rows = data.get((c, arm))
                if not rows:
                    continue
                x = [float(r[axis]) for r in rows]
                y = [100 * int(r["covered"]) / int(r["reference"]) for r in rows]
                (line,) = ax.step(
                    x,
                    y,
                    where="post",
                    label=arm,
                    linestyle=":" if "extended" in arm else "-",
                )
                ax.plot(x[-1], y[-1], ".", color=line.get_color())
            ax.set_xscale("symlog", linthresh=[0.02, 10, 100][i])
            ax.set_xlim(left=0)
            ax.set_ylim(-1, 103)
            ax.set_title(c)
            ax.grid(alpha=0.2)
        legends = {}
        for ax in axes.flat:
            lines, labels = ax.get_legend_handles_labels()
            legends.update(zip(labels, lines))
        fig.legend(legends.values(), legends, loc="outside upper center", ncol=5)
        fig.supxlabel(label + " (linear near zero, logarithmic above)")
        fig.supylabel("Derived reference final rows covered (%)")
        svg = dest / (axis + ".svg")
        fig.savefig(svg, metadata={"Date": None})
        plt.close(fig)
        svg.write_text(
            "\n".join(line.rstrip() for line in svg.read_text().splitlines()) + "\n"
        )


if __name__ == "__main__":
    plot(Path(__file__).parent / "run-recall" / "cell-stream")
