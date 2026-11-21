"""Whole-path paired timing ratios under real discovery and the prepaid-address diagnostic."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
HERE=Path(__file__).resolve().parent


def draw(folder):
    rows={}
    for fn in ('results.json','deriche.json'):
        rows.update(json.loads((folder/fn).read_bytes()))
    c={'live-original':'#47657a','live-joint':'#167d76','positive-original':'#b2a1c1','positive-joint':'#775687'}
    ls=['Online, original','Online, combined','Replay, original','Replay, combined']
    with plt.rc_context({'svg.fonttype':'none','svg.hashsalt':'source-cell-blocks','font.family':'DejaVu Sans','font.size':9,
                         'axes.spines.top':False,'axes.spines.right':False}):
        fig,ax=plt.subplots(figsize=(8.7,4.5),layout='constrained')
        for j,((key,color),label) in enumerate(zip(c.items(),ls)):
            y=[(len(rows)-1-i)*3.3+(.9-j*.54) for i in range(len(rows))]
            x=[r[key]['median_ms']/r['vanilla']['median_ms'] for r in rows.values()]
            ax.barh(y,x,height=.46,color=color,label=label,zorder=2)
            for xx,yy in zip(x,y):ax.text(xx+.018,yy,f'{xx:.2f}×',va='center',fontsize=8)
        ax.set_yticks([(len(rows)-1-i)*3.3+.09 for i in range(len(rows))],list(rows))
        ax.set_xlabel('Resident inference time relative to the default CPU on the same input')
        for x,name in ((.5,'2× target'),(1.,'default CPU')):
            ax.axvline(x,color='#425b63',lw=.8,ls='--',zorder=3)
            ax.text(x,1.01,name,transform=ax.get_xaxis_transform(),ha='center',fontsize=8)
        ax.set_xlim(0,max(r[k]['median_ms']/r['vanilla']['median_ms'] for r in rows.values() for k in c)+.28)
        ax.legend(loc='upper center',bbox_to_anchor=(.49,-.12),ncol=4,frameon=False,fontsize=8)
        ax.grid(axis='x',color='#e5eaeb',lw=.7);ax.tick_params(axis='y',length=0)
        file=folder/'latency.svg';fig.savefig(file,metadata={'Date':None});plt.close(fig)
        file.write_text('\n'.join(line.rstrip() for line in file.read_text().splitlines())+'\n')

if __name__=='__main__':draw(HERE)
