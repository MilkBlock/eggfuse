"""Draw graph coverage and semantic decisions on distinct, full percentage axes."""
import csv
from html import escape
from pathlib import Path

BASE=Path(__file__).parent
def main():
    with (BASE/'results/metrics.tsv').open() as f:
        rs={r['model']:r for r in csv.DictReader(f,delimiter='\t') if r['subset']=='heldout' and r['state']=='all'}
    out=['<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="312" viewBox="0 0 1080 312"><title>Held-out semantic decisions and whole-graph generation</title><rect width="1080" height="312" fill="#f6f8f7"/>']
    def text(x,y,t,size=15,anchor='start',color='#193443'):
        out.append(f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-family="Arial,sans-serif" font-size="{size}" fill="{color}">{escape(str(t))}</text>')
    def line(x,y,xx,yy,c,width=1):
        out.append(f'<line x1="{x}" y1="{y}" x2="{xx}" y2="{yy}" stroke="{c}" stroke-width="{width}"/>')
    text(18,26,'FIGURE 20    /    TWO SEPARATE ENDPOINTS',18)
    for j,(title,correct,den) in enumerate((('Request equality · accuracy','all_correct','all_tests'),
                                         ('Second Run · complete nonempty','nonempty_complete','nonempty'))):
        left=12+535*j
        out.append(f'<rect x="{left}" y="42" width="523" height="258" rx="8" fill="white" stroke="#cedbdd"/>')
        text(left+18,69,title,20);x0=left+125
        for tick in [0,25,50,75,100]:
            x=x0+tick*3.75
            line(x,85,x,245,'#dae3e5');text(x,264,str(tick)+'%',12,'middle')
        for i,(arm,lab) in enumerate([('explicit','Ports'),('singleton','Singleton'),('pairwise','Pairwise'),('incidence','Class nodes')]):
            y=105+i*42;text(left+13,y+5,lab,14)
            for seed,dy,col in [(1703,-5,'#247568'),(1709,6,'#76528f')]:
                r=rs[f'{arm}-{seed}'];v=100*int(r[correct])/int(r[den]);x=x0+v*3.75
                line(x0,y+dy,x,y+dy,col,2.2)
                out.append(f'<circle cx="{x}" cy="{y+dy}" r="3.6" fill="{col}"/>')
    text(54,289,'1703',13,color='#247568');text(115,289,'1709',13,color='#76528f');text(613,289,'384 graphs  /  3 source rules in 2 held-out families',13)
    (BASE/'results/ablation.svg').write_text(''.join(out)+'</svg>\n')
if __name__=='__main__':main()
