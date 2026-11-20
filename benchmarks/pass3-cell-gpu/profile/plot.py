"""Original and optimized Pass 3 GPU stage times from real encoder timestamps."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
data=json.loads((HERE/'results/profile.json').read_text())['cases']
matplotlib.rcParams.update({'svg.fonttype':'none','svg.hashsalt':'pass3-profile-v1','font.size':10})
fig,axes=plt.subplots(1,2,figsize=(10.6,3.0),sharey=True,layout='constrained')
groups=['entry','tokens','rhs','repair','spine','control']
labels=['Entry matching','Token build + dedup','Ordered RHS','Union + rebuild','Spine','Control']
for ax,(name,d) in zip(axes,data.items()):
    for y,key in enumerate(groups):
        a=d['modes']['baseline']['detail']['groups_ms'][key];b=d['modes']['prefix']['detail']['groups_ms'][key]
        ax.hlines(y,min(a,b),max(a,b),color='#91a4ad',linewidth=2)
        ax.scatter(a,y,s=36,color='#294e72',zorder=2)
        ax.scatter(b,y,s=30,color='#26816f',marker='s',zorder=3)
        ax.annotate(f'{a:.0f} → {b:.0f}',(max(a,b),y),xytext=(6,0),textcoords='offset points',va='center',fontsize=8)
    ax.set_xscale('log');ax.set_xlim(6,8000);ax.set_title(name);ax.set_xlabel('Cumulative encoder time (ms, log scale)')
    ax.grid(axis='x',alpha=.16);ax.spines[['right','top']].set_visible(False)
axes[0].set_yticks(range(len(labels)),labels);axes[0].invert_yaxis()
fig.legend(handles=[Line2D([0],[0],marker='o',linestyle='',color='#294e72',label='Before'),Line2D([0],[0],marker='s',linestyle='',color='#26816f',label='After')],
           loc='upper right',bbox_to_anchor=(.97,1.04),ncols=2,frameon=False,fontsize=8)
dest=ROOT/'docs/cell-architecture-atlas/figures/31-gpu-phases.svg'
fig.savefig(dest,metadata={'Date':None})
dest.write_text('\n'.join(s.rstrip() for s in dest.read_text().splitlines())+'\n')
