"""Render allocator measurements and actual release/retirement counts."""
import csv
import json
from pathlib import Path
from statistics import median

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parent/'results'
COLORS=['#365e83','#168472','#a4572c']
matplotlib.rcParams.update({'svg.fonttype':'none','svg.hashsalt':'eggfuse-integral-18','font.size':9})
curves=json.loads((ROOT/'allocation.json').read_text())
with (ROOT/'metrics.tsv').open() as source:
    counts={r['mode']:r for r in csv.DictReader(source,delimiter='\t') if r['seed']=='1703' and r['panel']=='heldout'}
fig,(left,right)=plt.subplots(1,2,figsize=(9.6,3.3),layout='constrained',gridspec_kw={'width_ratios':[1,1.15]})
modes=('source','primary','integral')
for mode,color in zip(modes,COLORS):
    measured=[r['stages'] for r in curves if r['mode']==mode and not r['fixed']]
    vals=[median(s[i]['arena_page_bytes'] for s in measured)/2**20 for i in range(4)]
    left.plot(range(4),vals,marker='o',color=color,label=mode)
left.set(xticks=range(4),xticklabels=['Ingress','A','B','C'],yticks=[0,3.5,7,10.5,14],
         ylabel='Allocated member pages (MiB)',title='16,384 graphs on one GPU')
left.legend(frameon=False)
for y,mode in enumerate(('stable_integral','primary','integral')):
    r=counts[mode]
    valid=sum(int(r[f'reuse_{j}']) for j in range(4))
    expired=sum(int(r[f'invalid_{j}']) for j in range(4))
    right.barh(y,valid,color='#168472',height=.48,label='Reused at release' if y==0 else None)
    right.barh(y,expired,left=valid,color='#d99659',height=.48,label='Retired early' if y==0 else None)
    right.text(valid*.5,y,f'{valid:,}',ha='center',va='center',color='white')
    if expired:right.text(valid+expired+50,y,str(expired),va='center',fontsize=8)
right.set(yticks=range(3),yticklabels=['Stable equality','Primary exit','Integral exit'],xlim=(0,5300),
          xlabel='Private member allocations',title='384 held-out graphs')
right.legend(loc='lower left',bbox_to_anchor=(0,1.11),ncols=2,frameon=False,fontsize=8)
for ax in (left,right):
    ax.spines[['top','right']].set_visible(False)
fig.savefig(ROOT/'allocation.svg',metadata={'Date':None})
svg=ROOT/'allocation.svg'
svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
