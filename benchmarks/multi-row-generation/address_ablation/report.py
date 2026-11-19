"""Tabular address statistics and a full-scale accuracy figure for the frozen report."""
import argparse
import csv
import json
from pathlib import Path
from statistics import median

HERE=Path(__file__).resolve().parent


def figure(rows,path):
    colors={'flat':'#38688b','two':'#735199','three':'#b97b23','packed':'#257764'}
    groups=('new_rows','new_port','large')
    out=['<svg xmlns="http://www.w3.org/2000/svg" width="1020" height="278" viewBox="0 0 1020 278"><title>Second Run exact witness accuracy by address layout and seed</title><rect width="100%" height="100%" fill="#f4f7f7"/>']
    def text(x,y,t,size=14):
        out.append(f'<text x="{x}" y="{y}" font-family="Arial,sans-serif" font-size="{size}" fill="#213a4b">{t}</text>')
    text(20,28,'FIGURE 03   /   SECOND-RUN WITNESS ACCURACY',18)
    text(655,28,'circle 1703     square 1709',14)
    for i,(panel,label) in enumerate(zip(groups,['New rows · 6×2×3','New port · 4×3×4','Larger graph · 8×6×4'])):
        x=13+i*335
        out.append(f'<rect x="{x}" y="43" width="323" height="220" rx="8" fill="#fff" stroke="#c8d6d6"/>')
        text(x+13,71,label,18)
        for j,arm in enumerate(colors):
            y=100+j*36;text(x+11,y+7,arm)
            left=x+77;w=222
            out.append(f'<path d="M{left} {y+2} h{w}" stroke="#d7dfe2"/>')
            for seed,dy in [('1703',-4),('1709',7)]:
                r=next(z for z in rows if z['panel']==panel and z['model']==f'{arm}-{seed}')
                k=left+w*r['run2_correct']/r['obligations_per_run']
                if seed=='1703':out.append(f'<circle cx="{k}" cy="{y+dy}" r="4" fill="{colors[arm]}"/>')
                else:out.append(f'<rect x="{k-3.5}" y="{y+dy-3.5}" width="7" height="7" fill="{colors[arm]}"/>')
        text(x+70,247,'0%');text(x+172,247,'50%');text(x+276,247,'100%')
    path.write_text(''.join(out)+'</svg>\n')


def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    r=json.loads((a.root/'results.json').read_text());rows=[];a.output.mkdir(parents=True,exist_ok=True)
    for panel,records in r['reports'].items():
        for name,m in records.items():
            row=dict(panel=panel,shape='x'.join(map(str,r['shapes'][panel])),model=name,graphs=m['graphs'],obligations_per_run=m['obligations_per_run'],whole_graphs=m['whole_graphs'])
            for s in ('run1','run2'):
                for k,v in m[s].items():
                    if not isinstance(v,list):row[s+'_'+k]=v
            timing=r['timings'][panel][name]
            row.update(median_ms=round(timing['median_ms'],4),timed_complete=timing['exact'],complete_graphs_per_second=round(timing['exact_graphs_per_second'],3))
            rows.append(row)
    with (a.output/'metrics.tsv').open('w') as f:
        w=csv.DictWriter(f,list(rows[0]),delimiter='\t',lineterminator='\n');w.writeheader();w.writerows(rows)
    figure(rows,a.output/'address-accuracy.svg')

if __name__=='__main__':main()
