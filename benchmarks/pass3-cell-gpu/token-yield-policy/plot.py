"""Compare effective origin yield and time to a calibrated RSS increment."""
import json
from pathlib import Path
import sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent
ARMS=("raw","filter","packed","ports","fraction")
LABELS=("Original","Filter","Packed","+ ports","+ pool")
COLORS=("#798994","#478580","#306b9b","#8c6c91","#b6782b")


def plot(out):
    data=json.loads((HERE/"scorecard.json").read_bytes())
    with plt.rc_context({"font.size":9,"svg.fonttype":"none","svg.hashsalt":"token-return-rss"}):
        fig,axes=plt.subplots(1,2,figsize=(9.6,3.7),sharey=True)
        for ax,(case,rows) in zip(axes,data.items()):
            for i,arm in enumerate(ARMS):
                r=rows[arm]
                ax.scatter(r["time_ms"],r["effective_per_packet"],s=65,color=COLORS[i],
                           marker=("o","s","D","v","^")[i],label=LABELS[i],zorder=3)
            ax.set_title(f"{case} (+{rows['raw']['delta_kib']/1024:.2f} MiB)")
            ax.set_xlabel("Time to common RSS rise (ms), lower is earlier")
            ax.margins(x=.13)
            ax.set_ylim(.075,.226)
            ax.grid(alpha=.23)
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
        axes[0].set_ylabel("Visible origins / emitted explicit proposal")
        fig.legend(*axes[0].get_legend_handles_labels(),loc="lower center",frameon=False,ncol=5)
        fig.tight_layout(rect=(0,.11,1,1))
        fig.savefig(out,metadata={"Date":None});plt.close(fig)
    out.write_text("\n".join(s.rstrip() for s in out.read_text().splitlines())+"\n")

if __name__=="__main__":
    plot(Path(sys.argv[1]))
