"""Plot hard deadline vs proved completion and throughput at matched correctness."""
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parent/'results'
with (ROOT/'metrics.tsv').open() as f:rows=list(csv.DictReader(f,delimiter='\t'))
time=json.loads((ROOT/'summary.json').read_text())['timings']
matplotlib.rcParams.update({'svg.fonttype':'none','svg.hashsalt':'eggfuse-stop-19','font.size':9})
fig,(ax,bar)=plt.subplots(1,2,figsize=(10,3.2),layout='constrained',gridspec_kw={'width_ratios':[1.22,1]})
for key,label,color,style in [('exact','Exact closure','#167364','-'),('fixed4','Fixed K=4','#475b78','--'),
                              ('fixed8','Fixed K=8','#916920',':'),('ledger_guard','Learned + guard','#824781','-.'),
                              ('blind_raw','Blind, unguarded','#b45442','--')]:
    entries=[r for r in rows if [r[k] for k in ('seed','panel','transport','lane')]==['1703','heldout','ordinary',key]]
    ax.plot([int(r['budget']) for r in entries],[int(r['complete']) for r in entries],label=label,c=color,ls=style,marker='.',ms=5)
ax.set(xlabel='GPU scheduler tick budget',ylabel='Graphs with proved completion / 384',title='Same deadline')
ax.legend(fontsize=7,frameon=False,loc='lower right',ncols=2)
lanes=['exact','fixed4','fixed8','ledger_guard','blind_guard']
for s,offset,c in [('1703',-.18,'#467190'),('1709',.18,'#378a75')]:
    vals=[time[f'{s}/heldout/ordinary/{lane}']['correct_per_second'] for lane in lanes]
    bar.barh([i+offset for i in range(len(lanes))],vals,height=.32,color=c,label=s)
bar.set(yticks=range(5),yticklabels=['Exact','K=4','K=8','Gate + guard','Blind + guard'],
        xlabel='Correct nonempty graphs / second',title='All 384 graphs pass at 48 ticks')
bar.legend(fontsize=8,frameon=False,loc='upper left',bbox_to_anchor=(0,1.18),ncols=2)
for a in (ax,bar):a.spines[['top','right']].set_visible(False)
p=ROOT/'budget.svg';fig.savefig(p,metadata={'Date':None})
p.write_text('\n'.join(line.rstrip() for line in p.read_text().splitlines())+'\n')
