"""Normalized paired resident times; oracle bars retain the native verifier."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent


def plot(folder):
    data={}
    for filename in ('results.json','deriche.json'):
        data.update(json.loads((folder/filename).read_bytes()))
    colors={'live':'#1d6671','all':'#a79bbe','positive':'#77618f'}
    labels={'live':'Online model','all':'Replay all addresses','positive':'Replay accepted addresses'}
    with plt.rc_context({'svg.fonttype':'none','svg.hashsalt':'source-receipt-ceiling','font.family':'DejaVu Sans',
                         'axes.spines.top':False,'axes.spines.right':False,'font.size':10}):
        fig,ax=plt.subplots(figsize=(8.4,4.9),layout='constrained')
        for j,arm in enumerate(colors):
            ys=[3*(len(data)-1-i)+(1-j)*.68 for i in range(len(data))]
            xs=[r[arm]['median_ms']/r['vanilla']['median_ms'] for r in data.values()]
            ax.barh(ys,xs,height=.58,color=colors[arm],label=labels[arm],zorder=2)
            for x,y in zip(xs,ys):
                ax.text(x+.025,y,f'{x:.2f}×',va='center',fontsize=9)
        ax.set_yticks([3*(len(data)-1-i) for i in range(len(data))],list(data))
        ax.set_xlabel('Resident inference time / paired default CPU time')
        for x,name in [(.5,'2× target'),(1.,'default CPU')]:
            ax.axvline(x,color='#344454',ls='--',lw=.9,zorder=3)
            ax.text(x,1.01,name,ha='center',va='bottom',transform=ax.get_xaxis_transform(),fontsize=8)
        ax.set_xlim(0,max(r['live']['median_ms']/r['vanilla']['median_ms'] for r in data.values())+.30)
        ax.legend(loc='upper center',bbox_to_anchor=(.51,-.13),ncol=3,frameon=False,fontsize=9)
        ax.tick_params(axis='y',length=0);ax.grid(axis='x',color='#e4e9ea',lw=.65,zorder=0)
        fig.savefig(folder/'latency.svg',metadata={'Date':None});plt.close(fig)

if __name__=='__main__':plot(HERE)
