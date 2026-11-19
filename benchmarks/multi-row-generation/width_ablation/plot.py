"""Two axes: fraction of exact graphs and measured two-Run latency."""
import csv
from pathlib import Path

ROOT=Path(__file__).parent/'results'

def main():
    with (ROOT/'metrics.tsv').open() as f:
        data={r['case']:r for r in csv.DictReader(f,delimiter='\t') if r['subset']=='all'}
    svg=['<svg xmlns="http://www.w3.org/2000/svg" width="940" height="275" viewBox="0 0 940 275"><title>Single-row weights expanded without training</title><rect width="940" height="275" fill="#f4f7f7"/>']
    def text(x,y,t,size=15,color='#233b4e',anchor='start'):
        svg.append(f'<text x="{x}" y="{y}" font-family="Arial,sans-serif" fill="{color}" font-size="{size}" text-anchor="{anchor}">{t}</text>')
    text(20,28,'FIGURE 04   /   ZERO-SHOT WIDTH EXPANSION',18)
    for idx,label in enumerate(('Complete nonempty graphs / 768','Latency per graph, ms')):
        start=16+460*idx
        svg.append(f'<rect x="{start}" y="44" width="445" height="214" rx="7" fill="white" stroke="#d2dbde"/>')
        text(start+13,69,label,17)
        high=(400,10)[idx];base=214
        for v in (0,high/2,high):
            y=base-v/high*116
            svg.append(f'<path d="M{start+44} {y} h379" stroke="#d2dbde"/>');text(start+34,y+4,f'{v:g}',12,anchor='end')
        for seed,color in ((1703,'#1c7464'),(1709,'#75548e')):
            points=[]
            for j,width in enumerate((1,2,4)):
                row=data[f'{seed}-{width}x{width}-parallel']
                val=float(row['nonempty_complete_graphs' if idx==0 else 'median_ms'])
                x=start+86+j*143+(-2.5 if seed==1703 else 2.5);y=base-val/high*116;points.append(f'{x},{y}')
                svg.append(f'<circle cx="{x}" cy="{y}" r="4" fill="{color}"/>')
                if seed==1703:text(x+2.5,239,f'{width} × {8//width}',14,anchor='middle')
            svg.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="{color}" stroke-width="2"/>')
    text(695,28,'seed 1703',14,'#1c7464');text(797,28,'seed 1709',14,'#75548e')
    (ROOT/'expansion.svg').write_text(''.join(svg)+'</svg>\n')

if __name__=='__main__':main()
