"""Report accuracy, actual score invocations and paired wall time by policy."""
import argparse
import csv
import json
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('out',type=Path);a=p.parse_args()
    r=json.loads((a.root/'results.json').read_text());rows=[];buckets=[]
    for lane,v in r['totals'].items():
        score=v['r2'];t=v.get('timed',{});e=v.get('execution',{})
        row=dict(lane=lane,graphs=score['nonempty_graphs'],complete=score['nonempty_complete_graphs'],
                 repeats=score['duplicates'],missing=score['missing'],wrong_parent=score['wrong_parent'],
                 make_open=v['gate']['run1']['open_slots'],finish_open=v['gate']['run2']['open_slots'],
                 make_skipped=e.get('run1',{}).get('skipped_scorer_rows','NA'),
                 finish_skipped=e.get('run2',{}).get('skipped_scorer_rows','NA'),
                 median_ms=t.get('median_ms','NA'),timed_complete=t.get('successes','NA'),
                 complete_graphs_per_second=t.get('complete_per_second','NA'))
        rows.append(row)
        for bucket,stats in v['gate']['run2']['by_ready_obligations'].items():
            buckets.append(dict(lane=lane,ready_obligations_per_graph=bucket,graphs=stats['graphs'],complete=stats['complete'],
                                mean_open=round(stats['open_slots']/stats['graphs'],5),missing=stats['missing'],duplicates=stats['duplicates']))
    a.out.mkdir(exist_ok=True,parents=True)
    for file,entries in [('lanes.tsv',rows),('ready.tsv',buckets)]:
        with (a.out/file).open('w') as f:
            writer=csv.DictWriter(f,list(entries[0]),delimiter='\t',lineterminator='\n');writer.writeheader();writer.writerows(entries)
    draw(r,a.out)

def draw(r,out):
    s=['<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="310" viewBox="0 0 1000 310"><title>Learned row gates and compute at matched decisions</title><rect width="100%" height="100%" fill="#f4f7f6"/>']
    def text(x,y,t,size=14,anchor='start',color='#213a49'):
        s.append(f'<text x="{x}" y="{y}" font-family="Arial,sans-serif" font-size="{size}" fill="{color}" text-anchor="{anchor}">{t}</text>')
    text(18,28,'FIGURE 06   /   COMPUTE SKIPPED BY THE CALIBRATED GATE',18)
    for index,seed in enumerate((1703,1709)):
        v=r['totals'][f'p25-calibrated-metal_skip-{seed}'];left=12+494*index
        s.append(f'<rect x="{left}" y="45" width="480" height="245" rx="8" fill="white" stroke="#cedcdd"/>')
        text(left+16,72,'Seed '+str(seed),19);text(left+16,99,f"finish exact: {v['r2']['nonempty_complete_graphs']} / 768",15)
        for j,stage in enumerate(('run1','run2')):
            stats=v['execution'][stage];total=stats['candidate_rows'];skipped=stats['skipped_scorer_rows'];opened=total-skipped
            y=136+j*54;bar=320;start=left+96
            text(left+15,y+5,'make' if j==0 else 'finish')
            s.append(f'<rect x="{start}" y="{y-12}" width="{bar}" height="22" fill="#e5e9e8"/>')
            s.append(f'<rect x="{start}" y="{y-12}" width="{bar*opened/total:.2f}" height="22" fill="#337e73"/>')
            text(start,y+28,f'{opened:,} executed   /   {skipped:,} skipped',13)
        g=v['gate']['run2']['open_rows_hist_by_round']
        text(left+16,260,'Two rows active per round: '+', '.join(str(x[2]) for x in g)+' graphs',14)
    (out/'gates.svg').write_text(''.join(s)+'</svg>\n')

if __name__=='__main__':main()
