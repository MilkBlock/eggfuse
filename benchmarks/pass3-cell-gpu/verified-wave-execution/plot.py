"""Plot each full method against the vanilla measurement on the same source."""
import json
from pathlib import Path
import sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent


def plot(out):
    data={}
    for name in ("small.json","large.json"):
        data.update(json.loads((HERE/name).read_bytes()))
    order=("sum-bits","dot-product","conjugate-gradient","3mm","deriche")
    configs=(("off","Original issuer"),("filter","Reject impossible"),("packed","+ compact queue"),
             ("ports","+ positive ports"),("pool","+ predicted pool"))
    with plt.rc_context({"font.size":9,"svg.fonttype":"none","svg.hashsalt":"verified-wave-performance"}):
        fig,ax=plt.subplots(figsize=(9.2,4.5))
        colors=("#397581","#a86b32","#805d91","#315c44","#645855")
        for j,case in enumerate(order):
            v=data[case]
            ratio=[v[k]["median_ms"]/v["vanilla"]["median_ms"] for k,_ in configs]
            ax.plot(range(len(configs)),ratio,marker=("o","s","D","^","v")[j],color=colors[j],label=case,linewidth=1.6)
        ax.axhline(1,color="#343434",ls="--",lw=1)
        ax.axhline(.5,color="#343434",ls=":",lw=1)
        ax.text(.02,1.04,"Exact CPU",fontsize=8)
        ax.text(.02,.54,"2× faster than exact CPU",fontsize=8)
        ax.set(ylabel="Full inference time / exact CPU time",xticks=range(len(configs)),
               xticklabels=[title for _,title in configs],ylim=(.35,None))
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.grid(axis="y",alpha=.16)
        fig.legend(*ax.get_legend_handles_labels(),loc="lower center",ncol=5,frameon=False)
        fig.tight_layout(rect=(0,.08,1,1))
        fig.savefig(out,metadata={"Date":None})
        plt.close(fig)
    out.write_text("\n".join(l.rstrip() for l in out.read_text().splitlines())+"\n")


if __name__=="__main__":
    plot(Path(sys.argv[1]))
