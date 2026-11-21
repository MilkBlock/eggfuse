"""Render held-out physical placement and the four complete inference samples."""
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent


def plot(out):
    data = json.loads((HERE / "results.json").read_bytes())
    labels = ("Exact CPU", "Issuer only", "First K", "Linear BCE", "Linear quota", "MLP BCE", "MLP quota")
    arms = ("vanilla", "off", "first", "bce-0", "quota-0", "bce-8", "quota-8")
    colors = ("#334c5a", "#718791", "#839496", "#197460", "#197460", "#674992", "#674992")
    with plt.rc_context({"font.size": 10, "svg.fonttype": "none", "svg.hashsalt": "placement-1703"}):
        fig, axes = plt.subplots(2, 2, figsize=(10, 5.4), sharey=True)
        for row, (case, group) in enumerate(data.items()):
            allocation, runtime = axes[row]
            ceiling = group["first"]["rank"]["oracle_fresh"]
            for y, (arm, color) in enumerate(zip(arms, colors)):
                item = group[arm]
                if arm not in ("vanilla", "off"):
                    hit = item["rank"]["selected_fresh"] / ceiling * 100
                    allocation.barh(y, hit, height=.56, color=color)
                    allocation.text(hit+1, y, f"{hit:.1f}%", fontsize=8, va="center")
                runtime.scatter(item["ms"], [y]*len(item["ms"]), marker="|", s=48, color=color, alpha=.8)
                runtime.scatter(item["median_ms"], y, s=26, color=color)
            allocation.set(xlim=(0, 103), yticks=range(len(labels)), yticklabels=labels)
            allocation.axvline(100, ls=":", color="#465b68")
            for ax in (allocation, runtime):
                ax.grid(True, axis="x", alpha=.2)
                ax.set_axisbelow(True)
                ax.set_title(case)
                ax.spines["top"].set_visible(False)
                ax.spines["right"].set_visible(False)
        axes[0, 0].invert_yaxis()
        axes[1, 0].set_xlabel("Hits / best possible at frozen rule quotas (%)")
        axes[1, 1].set_xlabel("Full inference (ms), mark = run, dot = median")
        fig.tight_layout()
        fig.savefig(out, metadata={"Date": None})
        plt.close(fig)
    out.write_text("\n".join(line.rstrip() for line in out.read_text().splitlines())+"\n")


if __name__ == "__main__":
    plot(Path(sys.argv[1]))
