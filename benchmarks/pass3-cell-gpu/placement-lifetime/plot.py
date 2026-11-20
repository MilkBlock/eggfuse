"""Render native retained-graph and cumulative-allocation curves on their own scales."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def plot(folder,out):
    cases=('gemm-bias-relu','gated-state')
    arms=[('pooled/keep','Stock pooling','#292d30'),('multi-prefix/keep','Multi-member prefix','#5c8db1'),
          ('defer/keep','All extendable prefixes','#c78832'),('defer/retrained','All prefixes + trained gate','#08796d')]
    with plt.rc_context({'font.family':'DejaVu Sans','font.size':9,'svg.fonttype':'none','svg.hashsalt':'eggfuse-lifetime'}):
        fig,ax=plt.subplots(3,2,figsize=(9,7.4),sharex='col',layout='constrained')
        for j,name in enumerate(cases):
            rows=json.loads((folder/(name+'.json')).read_bytes())
            base=rows['pooled/keep']['curve']
            for label,title,color in arms:
                pts=rows[label]['curve']
                live=[(r[0],(r[1]-b[1])/1024) for r,b in zip(pts,base) if r[1] and b[1]]
                ax[0,j].plot(*zip(*live),lw=1.4,color=color,label=title)
                area=[]
                total=0.
                for run,kib in live:
                    if run:total+=kib/1024
                    area.append(total)
                ax[1,j].plot([r for r,_ in live],area,lw=1.4,color=color)
                ax[2,j].plot([r[0] for r in pts],[(r[3]-b[3])/1048576 for r,b in zip(pts,base)],lw=1.4,color=color)
            ax[0,j].set_title(name)
            ax[2,j].set_xlabel('Source Run')
            for a in ax[:,j]:
                a.grid(axis='y',alpha=.24)
                a.spines[['top','right']].set_visible(False)
        ax[0,0].set_ylabel('Live graph Δ (KiB)')
        ax[1,0].set_ylabel('Integrated graph Δ (MiB·Runs)')
        ax[2,0].set_ylabel('Cumulative requested Δ (MiB)')
        fig.legend(*ax[0,0].get_legend_handles_labels(),loc='outside lower center',ncol=2,frameon=False)
        fig.suptitle('Placement cost relative to stock pooling',fontsize=13)
        fig.savefig(out,metadata={'Date':None})
        plt.close(fig)
    if out.suffix=='.svg':
        out.write_text('\n'.join(line.rstrip() for line in out.read_text().splitlines())+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('folder',type=Path);p.add_argument('out',type=Path)
    a=p.parse_args();plot(a.folder,a.out)
