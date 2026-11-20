"""Render every recorded source Run (no decimation), using a separate physical-unit axis per row."""
import csv,math
from pathlib import Path

ROOT=Path(__file__).resolve().parent
data=list(csv.DictReader((ROOT/'storage-curves.tsv').open(),delimiter='\t'))
parts=['<svg xmlns="http://www.w3.org/2000/svg" width="940" height="660" viewBox="0 0 940 660">',
'<title>Matched online storage across the full source schedule</title>','<rect width="100%" height="100%" fill="white"/>',
'<g font-family="Arial, sans-serif" fill="#243841">']
def label(x,y,s,size=12,extra=''):
    parts.append(f'<text x="{x}" y="{y}" font-size="{size}" {extra}>{s}</text>')
colors={'dynamic':'#834b41','leaf':'#3e719f','composed':'#267767'}
label(24,32,'What is retained as Pass 3 advances?',24,'font-weight="bold"')
for j,(mode,color) in enumerate(colors.items()):
    x=535+j*124;parts.append(f'<line x1="{x}" x2="{x+23}" y1="26" y2="26" stroke="{color}" stroke-width="3"/>')
    label(x+28,31,mode)
for column,case in enumerate(('sum-bits','dot-product')):
    x=76+column*458;w=378
    label(x,68,case,17,'font-weight="bold"')
    groups={mode:[r for r in data if r['arm']==mode and r['workload']==case] for mode in colors}
    for row,(field,title,unit) in enumerate([('requested_heap_bytes','Requested heap above first boundary','MiB'),('rss_after_bytes','Resident memory','MiB'),('integral_instances','Live integral owners','owners')]):
        top=101+row*176;height=112
        label(x,top-8,title+' ('+unit+')',13)
        vals={m:[(int(r[field])-(int(rs[0][field]) if row==0 else 0))/(2**20 if row<2 else 1) for r in rs] for m,rs in groups.items()}
        lo=math.floor(min(min(v) for v in vals.values()));hi=math.ceil(max(max(v) for v in vals.values()))
        if row==2:lo=0;hi=math.ceil(hi/100)*100
        if hi==lo:hi+=1
        for frac in (0,.5,1):
            y=top+height*(1-frac)
            parts.append(f'<line x1="{x}" x2="{x+w}" y1="{y}" y2="{y}" stroke="#d9e2e6"/>')
            label(x-7,y+4,f'{lo+frac*(hi-lo):g}',11,'text-anchor="end"')
        for mode,v in vals.items():
            pts=' '.join(f'{x+i*w/(len(v)-1):.2f},{top+height*(hi-y)/(hi-lo):.2f}' for i,y in enumerate(v))
            parts.append(f'<polyline points="{pts}" fill="none" stroke="{colors[mode]}" stroke-width="1.35" opacity="0.9"/>')
        for frac in (0,.5,1):label(x+frac*w,top+height+15,str(round(1+frac*(len(v)-1))),10,'text-anchor="middle"')
        label(x+w/2,top+height+31,'Source Run',11,'text-anchor="middle"')
label(24,645,'Counted allocator and boundary RSS run separately from the timing samples. Each line contains every Run.',12)
parts.append('</g></svg>');(ROOT/'storage-curves.svg').write_text('\n'.join(parts)+'\n')
