"""Plot complete native budgets and the fixed-corpus exposure curve from exported text."""
import argparse
import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def plot(d):
    with (d/"budget-curves.csv").open() as f:
        rows=list(csv.DictReader(f))
    with (d/"training.csv").open() as f:
        fits=list(csv.DictReader(f))
    checkpoints=["local-s71-t100000"]+["A/local-s71-t%d"%x for x in (250000,500000,1000000)]
    labels=["100K","250K","500K","1M"]
    fig,axes=plt.subplots(2,2,figsize=(10,7.5),constrained_layout=True)
    for ax,case in zip(axes.flat,["sum-divisors","shared-polynomial","crossed-difference"]):
        for name,label in zip(["random","history"]+checkpoints,["Factorized random","Historical Stream"]+labels):
            subset=defaultdict(list)
            for r in rows:
                if (r["model"]==name and r["case"]==case and r["mode"]=="continuation"
                    and r["unique"]=="True" and int(r["shortfall"])==0):
                    subset[int(r["budget"])].append(int(r["ops"]))
            if subset:
                x=sorted(subset)
                ax.plot(x,[mean(subset[v]) for v in x],marker="o",markersize=3,label=label)
        ax.set(xlabel="Paid requests after first productive request",ylabel="Additional effective operations",title=case,
               xscale="log", xlim=(14,285))
        ax.set_xticks([16,32,64,128,256], labels=["16","32","64","128","256"])
        ax.grid(alpha=.2)
    ax=axes.flat[-1]
    by_name={r["model"]:r for r in fits}
    x=[int(by_name[k]["exposures"]) for k in checkpoints if k in by_name]
    for field,label in [("interval_train_ce","Training (interval)"),("validation_ce","Validation (fixed probes)")]:
        if x and all(by_name[k].get(field) for k in checkpoints if k in by_name):
            ax.plot(x,[float(by_name[k][field]) for k in checkpoints if k in by_name],marker="o",label=label)
    ax.set(xlabel="Cumulative complete-token exposures",ylabel="Complete-token CE",title="Fixed corpus, local parameters",
           xscale="log",xlim=(90000,1100000))
    ax.set_xticks([100000,250000,500000,1000000],labels=labels)
    ax.legend(fontsize=8); ax.grid(alpha=.2)
    axes.flat[0].legend(fontsize=7)
    fig.savefig(d/"continuation.png",dpi=150)
    plt.close(fig)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("directory",type=Path)
    plot(parser.parse_args().directory)
