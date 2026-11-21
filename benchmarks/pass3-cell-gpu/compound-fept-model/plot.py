"""Plot the measured external transport yield and origins per charged step."""
import json
import sys
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
HERE=Path(__file__).resolve().parent
def plot(out):
    data=json.loads((HERE/"results.json").read_bytes())
    data.update(json.loads((HERE/"deriche.json").read_bytes()))
    with plt.rc_context({"font.size":9,"svg.hashsalt":"native-compound-fept","svg.fonttype":"none"}):
        fig,axes=plt.subplots(1,2,figsize=(9.3,4.2))
        for ax,metric,title in zip(axes,("forward","decisions_plus_return"),("External transport yield","Yield including prototype work and replies")):
            for c,color,marker in (("sum-bits","#507a8e","s"),("3mm","#23674e","o"),("deriche","#955627","D")):
                a=data[c]["arms"]
                ax.plot(range(4),[a[k]["per_packet"][metric] for k in ("packed","singleton","wide","compound")],
                        marker=marker,color=color,label=c,linewidth=1.7)
            ax.set(xticks=range(4),xticklabels=["Literal","RL class","+ wide pair","+ arithmetic"],title=title,ylim=(0,None))
            ax.grid(axis="y",alpha=.2);ax.spines["top"].set_visible(False);ax.spines["right"].set_visible(False)
        axes[0].set_ylabel("Visible constructor origins / counted unit")
        fig.suptitle("Receiver-expanded group actions · transport diagnostics", fontsize=11)
        fig.legend(*axes[0].get_legend_handles_labels(),loc="lower center",frameon=False,ncol=3)
        fig.tight_layout(rect=(0,.08,1,.96));fig.savefig(out,metadata={"Date":None});plt.close(fig)
    out.write_text("\n".join(l.rstrip() for l in out.read_text().splitlines())+"\n")
if __name__=="__main__":plot(Path(sys.argv[1]))
