"""Render the per-seed Figure 05 table and chart from verified frozen results."""
import argparse
import csv
import json
from pathlib import Path


def main():
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('out',type=Path);a=p.parse_args()
    r=json.loads(a.source.read_text());rows=[];a.out.mkdir(exist_ok=True,parents=True)
    for name,out in r['totals'].items():
        score=out['r2'];time=out['timed']
        rows.append(dict(model=name,graphs=score['nonempty_graphs'],complete=score['nonempty_complete_graphs'],
                         wrong_parent=score['wrong_parent'],duplicates=score['duplicates'],same_round_cross_row=score['duplicate_same_round_cross_row'],
                         missing=score['missing'],obligations=score['obligations'],illegal=score['illegal'],active=score['active_outputs'],
                         parent_ready=score['parent_ready_nonempty_graphs'],median_ms=round(time['median_ms'],4),
                         timed_success=time['successes'],timed_graphs=time['graphs'],valid_per_s=round(time['complete_per_second'],3)))
    with (a.out/'metrics.tsv').open('w') as f:
        w=csv.DictWriter(f,list(rows[0]),delimiter='\t',lineterminator='\n');w.writeheader();w.writerows(rows)
    s=['<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="325" viewBox="0 0 1000 325"><title>Credit assignment and correct two-row inference</title><rect width="100%" height="100%" fill="#f5f8f7"/>']
    def text(x,y,t,size=15,anchor='start',color='#203b48'):
        s.append(f'<text x="{x}" y="{y}" font-family="Arial,sans-serif" text-anchor="{anchor}" fill="{color}" font-size="{size}">{t}</text>')
    text(20,30,'FIGURE 05  /  SAME TWO-ROW ACTOR AT DEPLOYMENT',19)
    arms=('zero','supervised','team','counterfactual');labels=('Zero updates','Set labels','Team RL','CF RL');colors=('#197868','#7c5189')
    for j,(title,field,high) in enumerate([('Complete nonempty graphs / 768','complete',400),('Measured valid graphs / second','valid_per_s',70)]):
        left=10+492*j;s.append(f'<rect x="{left}" y="46" width="482" height="261" rx="8" fill="white" stroke="#cedcdd"/>');text(left+12,71,title,18)
        axis=left+110;width=342
        for value in (0,high/2,high):
            x=axis+width*value/high;s.append(f'<path d="M{x} 84 v167" stroke="#dce4e5"/>');text(x,275,f'{value:g}',12,'middle')
        for i,(arm,label) in enumerate(zip(arms,labels)):
            y=106+i*44;text(left+12,y+4,label,14)
            for seed,dy,colour in zip((1703,1709),(-5,6),colors):
                val=next(row[field] for row in rows if row['model']==f'{arm}-{seed}')
                end=axis+width*val/high
                s.append(f'<path d="M{axis} {y+dy} H{end}" stroke="{colour}" stroke-width="3"/>')
                s.append(f'<circle cx="{end}" cy="{y+dy}" r="3.4" fill="{colour}"/>')
    text(740,29,'seed 1703',14,color=colors[0]);text(850,29,'seed 1709',14,color=colors[1])
    (a.out/'credit.svg').write_text(''.join(s)+'</svg>\n')

if __name__=='__main__':main()
