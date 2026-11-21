"""Plot the measured time to a common RSS increment together with strict FEPT."""
import json
import sys
from pathlib import Path
from statistics import median

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator,FormatStrFormatter

HERE=Path(__file__).resolve().parent
NAMES=("leaf","trace","ripsat","union")
LABELS=("Leaf","Trace Bake","RipSat","Trace + RipSat")
COLORS=("#4c6572","#92477c","#197064","#ae762b")


def plot(out):
    data=json.loads((HERE/"results.json").read_bytes())
    memory=json.loads((HERE/"rss.json").read_bytes())
    with plt.rc_context({"font.size":9,"svg.fonttype":"none","svg.hashsalt":"ripsat-neural-endpoints"}):
        fig,axes=plt.subplots(2,2,figsize=(10,5.8),sharey="row")
        for j,case in enumerate(("sum-bits","3mm")):
            ms=memory[case];study=data[case]["arms"]
            a,b=axes[0,j],axes[1,j]
            for i,(key,color) in enumerate(zip(NAMES,COLORS)):
                score=study[key]["fept"]
                a.scatter(score,i,s=47,color=color)
                samples=[r["crossings"]["increment"][1]/1000 for r in ms["arms"][key]]
                b.scatter(samples,[i]*len(samples),marker="|",s=90,color=color)
                b.scatter(median(samples),i,marker="o",s=37,color=color)
            a.set_title(case)
            a.set_xlabel("Final visible constructor origins / external proposal")
            a.xaxis.set_major_locator(MaxNLocator(nbins=4))
            a.xaxis.set_major_formatter(FormatStrFormatter("%.4f"))
            b.set_xlabel(f"Time to +{ms['thresholds_kib'][1]/1024:.2f} MiB (ms)")
            for g in (a,b):
                g.set_yticks(range(4));g.set_yticklabels(LABELS)
                g.grid(axis="x",alpha=.25)
                g.margins(x=.13,y=.15)
                g.spines["right"].set_visible(False);g.spines["top"].set_visible(False)
        for a in axes[:,0]:a.invert_yaxis()
        fig.tight_layout(h_pad=1.7)
        fig.savefig(out,metadata={"Date":None})
        plt.close(fig)
    out.write_text("\n".join(s.rstrip() for s in out.read_text().splitlines())+"\n")


if __name__=="__main__":plot(Path(sys.argv[1]))
