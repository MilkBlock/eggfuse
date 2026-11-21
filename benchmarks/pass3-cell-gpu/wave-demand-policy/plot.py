"""Plot actual private records constructed and consumed over the original Run schedule."""
import json
import sys
from itertools import accumulate
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent


def plot(out):
    curves = json.loads((HERE / "curves.json").read_bytes())
    labels = [("entry","Before issue","#536774"),("clip","Clip to sealed lanes","#bb782d"),
              ("fraction","Learn birth fraction","#846dad"),("coverage","Learn upper count","#197564")]
    with plt.rc_context({"font.size":9, "svg.fonttype":"none","svg.hashsalt":"wave-demand-2026"}):
        fig, axs = plt.subplots(2, 2, figsize=(9, 4.9), sharex="col")
        for j, case in enumerate(("sum-bits","3mm")):
            arms = curves[case]
            for name, label, color in labels:
                curve = arms[name]["curve"]
                xs = [row[0] for row in curve]
                for i, key in enumerate((3,4)):
                    ys = list(accumulate(row[key]/1000 for row in curve))
                    axs[i,j].plot(xs, ys, label=label, c=color)
            truth = arms["entry"]["curve"]
            axs[1,j].plot([r[0] for r in truth], list(accumulate(r[2]/1000 for r in truth)),
                          label="All fresh primary Cells",ls="--",c="#262525")
            axs[0,j].set_title(case)
            axs[1,j].set_xlabel("Source Run epoch")
            for ax in axs[:,j]:
                ax.spines["top"].set_visible(False)
                ax.spines["right"].set_visible(False)
                ax.grid(axis="y",alpha=.23)
        axs[0,0].set_ylabel("Grants (thousands)")
        axs[1,0].set_ylabel("Used (thousands)")
        fig.legend(*axs[1,0].get_legend_handles_labels(), loc="lower center", ncol=3, frameon=False)
        fig.tight_layout(rect=(0,.13,1,1))
        fig.savefig(out,metadata={"Date":None})
        plt.close(fig)
    out.write_text("\n".join(s.rstrip() for s in out.read_text().splitlines())+"\n")


if __name__ == "__main__":
    plot(Path(sys.argv[1]))
