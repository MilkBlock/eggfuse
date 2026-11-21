"""Show one prespecified fresh process per arm, aligned to its inference clock."""
from math import ceil, floor, log10
from pathlib import Path
from xml.sax.saxutils import escape
import json
from analyze import transform,progress
HERE=Path(__file__).resolve().parent
names={'cpu':('CPU','#222'), 'raw_external':('Raw','#866e22'),'filter_external':('Filter','#007966'),
       'raw_closed':('Closed','#654ca0'),'filter_closed':('Filter + closed','#2361b3'),
       'filter_mixed':('Filter + mixed','#cc3c47')}


def nice(v):
    z=10**floor(log10(max(v,1)/4))
    return next(k*z for k in (1,2,2.5,5,10) if k*z>=v/4)


def plot(case,cases,ev):
    arms={k:p[0]['sampled']['trace'] for k,p in cases['rows'].items()}
    raw=ev['arms']['raw_external']['ledger']['rows']
    chunks=['<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="820" viewBox="0 0 1080 820"><rect width="100%" height="100%" fill="white"/><g font-family="Arial,sans-serif" fill="#223044">']
    def txt(x,y,s,size=14,anchor='start',weight=400):
        chunks.append(f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" font-size="{size}" font-weight="{weight}">{escape(str(s))}</text>')
    def line(x1,y1,x2,y2,col,dash='none'):
        chunks.append(f'<path d="M{x1:.1f},{y1:.1f} L{x2:.1f},{y2:.1f}" stroke="{col}" stroke-dasharray="{dash}"/>')
    txt(65,34,case+' · inference-window RSS and actual wire traffic',23,weight=700)
    txt(65,60,'First prespecified fresh sampled process per arm. Progress is joined at the same completed original source Run.')
    for i,name in enumerate(arms):
        label,col=names[name];x=65+i*156;line(x,84,x+21,84,col);txt(x+26,89,label)
    time_limit=max(t[-1][0] for t in arms.values())/1000*1.02
    for h,title in enumerate(('Resident growth from inference entry (MiB)','External root wire avoided vs raw at the same Run (MiB)','Source-confirmed internal root commits')):
        y=129+h*223;top=y+14;bot=top+152
        xs=(91,1030)
        txt(xs[0],y,title,17,weight=700)
        points={}
        for name,t in arms.items():
            if h and name=='cpu':continue
            vals=[(r[1]-t[0][1])/1024 if h==0 else (progress(r,raw)['wire_bytes_avoided']/2**20 if h==1 else r[4]) for r in t]
            points[name]=vals
        low=min(0,min(min(v) for v in points.values()));high=max(1,max(max(v) for v in points.values()))
        step=nice(high-low);lo=floor(low/step)*step;hi=ceil(high/step)*step
        yy=lambda v:bot-(bot-top)*(v-lo)/(hi-lo)
        xx=lambda t:xs[0]+(xs[1]-xs[0])*t/time_limit
        for i in range(round((hi-lo)/step)+1):
            k=lo+i*step;line(xs[0],yy(k),xs[1],yy(k),'#e1e5eb');txt(xs[0]-7,yy(k)+4,f'{k:g}',12,'end')
        xt=nice(time_limit*.8)
        for i in range(floor(time_limit/xt)+1):
            t=i*xt;line(xx(t),top,xx(t),bot,'#e1e5eb');txt(xx(t),bot+17,f'{t:g}',12,'middle')
        if h==0:
            for (_,delta) in cases['thresholds_kib'].values():line(xs[0],yy(delta/1024),xs[1],yy(delta/1024),'#80858b','4 4')
        for name,v in points.items():
            ts=arms[name];stride=max(1,len(ts)//600);indices=sorted({0,len(ts)-1,v.index(max(v)),*range(0,len(ts),stride)})
            p=' '.join(f'{xx(ts[i][0]/1000):.1f},{yy(v[i]):.1f}' for i in indices)
            chunks.append(f'<polyline points="{p}" fill="none" stroke="{names[name][1]}" stroke-width="1.7"/>')
        txt(xs[1],bot+37,'elapsed inference (ms)',12,'end')
    txt(91,803,'Dashed RSS lines mark two independent CPU-calibrated growth targets. The exact CPU has no external neural packet stream.',12)
    (HERE/(case+'.svg')).write_text(''.join(chunks)+'</g></svg>\n')


if __name__=='__main__':
    cases=json.loads((HERE/'curves.json').read_bytes());evidence=json.loads((HERE/'audit.json').read_bytes())
    transform(cases,evidence,False)
    for case,data in cases.items():plot(case,data,evidence[case])
