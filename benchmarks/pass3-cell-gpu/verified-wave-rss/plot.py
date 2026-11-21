"""Draw inference-only RSS and observed physical Cell progress on the same clock."""
from itertools import accumulate
import json
from math import ceil, floor, log10
from pathlib import Path
from xml.sax.saxutils import escape

HERE=Path(__file__).resolve().parent
COLORS={'cpu':'#151515','raw':'#9a681e','filter':'#788e19','packed':'#007683','ports':'#6756a4',
        'fraction':'#1265bc','coverage':'#c23c43'}


def unpack(v):
    rows=v['trace_deltas']
    return list(zip(*(accumulate(column) for column in zip(*rows))))


def nice(maximum):
    rough=max(maximum,1)/4
    order=10**floor(log10(rough))
    return next(v*order for v in (1,2,2.5,5,10) if v*order>=rough)


def draw(case,raw,output):
    traces={name:unpack(pairs[0]['sampled']) for name,pairs in raw['rows'].items()}
    width,height=1080,810
    elements=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
              '<rect width="100%" height="100%" fill="white"/>',
              '<g font-family="Arial, sans-serif" fill="#202733">']
    def label(x,y,s,size=13,color=None,align='start',bold=False):
        elements.append(f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{align}" font-size="{size}" fill="{color or "#202733"}" font-weight="{700 if bold else 400}">{escape(str(s))}</text>')
    def line(x1,y1,x2,y2,c,dash='',thick=1):
        elements.append(f'<path d="M{x1:.2f},{y1:.2f} L{x2:.2f},{y2:.2f}" fill="none" stroke="{c}" stroke-width="{thick}" stroke-dasharray="{dash or "none"}"/>')
    label(63,31,f'{case} · native Pass 3 inference',23,bold=True)
    label(63,55,'First prespecified sampled replicate. Every line ends at the original inference exit.',14)
    for i,(name,col) in enumerate(COLORS.items()):
        x=66+i*135;line(x,77,x+24,77,col,thick=2.5);label(x+30,82,name)
    duration=max(t[-1][0]/1000 for t in traces.values());margin=min(10,duration*.02);xstep=nice((duration+margin)*.75)
    max_x=duration+margin
    left,right=90,1035
    def xx(t):return left+(right-left)*t/1000/max_x
    for panel,(y,title) in enumerate([(120,'Resident set size (MiB)'),(350,'RSS change since inference entry (MiB)'),(580,'Cumulative physical Cell records')]):
        label(left,y,title,17,bold=True)
        upper,lower=y+17,y+168
        vals=[[z[1]/1024 if panel==0 else (z[1]-t[0][1])/1024 if panel==1 else z[2] for z in t] for t in traces.values()]
        low=min(map(min,vals));high=max(map(max,vals));ystep=nice(high-low if panel==0 else high)
        mini=floor(min(low,high)/ystep)*ystep if panel==0 else min(0,floor(low/ystep)*ystep)
        maxi=max(mini+ystep,ceil(high/ystep)*ystep)
        def yy(v):return lower-(v-mini)/(maxi-mini)*(lower-upper)
        for i in range(round((maxi-mini)/ystep)+1):
            n=mini+i*ystep;line(left,yy(n),right,yy(n),'#e1e6eb');label(left-8,yy(n)+4,f'{n:g}',12,align='end')
        for i in range(floor(max_x/xstep)+1):
            v=i*xstep;x=left+(right-left)*v/max_x;line(x,upper,x,lower,'#e1e6eb');label(x,lower+17,f'{v:g}',12,align='middle')
        if panel<2:
            for frac,(ab,delta) in raw['thresholds_kib'].items():
                reference=(ab if panel==0 else delta)/1024
                if mini<=reference<=maxi:
                    line(left,yy(reference),right,yy(reference),'#888','4 4')
        for name,t in traces.items():
            if panel==2 and name not in ('fraction','coverage'):continue
            for col in ((2,3,4) if panel==2 else (1,)):
                vals=[(z[col] if panel==2 else (z[1]-(t[0][1] if panel==1 else 0))/1024) for z in t]
                stride=max(1,len(t)//550)
                idx=sorted({0,len(t)-1,vals.index(max(vals)),*range(0,len(t),stride)})
                coords=' '.join(f'{xx(t[i][0]):.1f},{yy(vals[i]):.1f}' for i in idx)
                dash={2:'2 4',3:'none',4:'8 4'}.get(col,'none')
                elements.append(f'<polyline points="{coords}" fill="none" stroke="{COLORS[name]}" stroke-width="1.65" stroke-linejoin="round" stroke-dasharray="{dash}"/>')
        label(right,lower+38,'elapsed inference (ms)',12,align='end')
    label(91,796,'Physical counts: dotted = prebuilt, solid = redeemed, dashed = expired unused. Horizontal dotted lines in the RSS panels mark the two CPU-calibrated thresholds.',12)
    output.write_text(''.join(elements)+'</g></svg>\n')


if __name__=='__main__':
    for case,raw in json.loads((HERE/'curves.json').read_bytes()).items():
        draw(case,raw,HERE/(case+'-rss.svg'))
