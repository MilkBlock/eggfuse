"""Charge the deployed first-placement scorer and physical maintenance in ordinary execution."""
import argparse,json,subprocess
from pathlib import Path
from statistics import median
from study import CASES,READ


def time(a):
    policies=READ(a.episodes/'policies.json')
    a.out.mkdir(parents=True,exist_ok=False);summary={}
    for name in CASES[2:]:
        rows={'stock':{},'score-pool':{},'terminal_saving':{},'owner_area_saving':{}}
        ref=READ(a.episodes/'deployment.json')[name]
        program=a.exp/'owner-action-fresh-v1'/name/'program.json'
        for trial in range(5):
            order=list(rows);i=trial%len(order);order=order[i:]+order[:i]
            for key in order if trial%2 else reversed(order):
                dst=a.out/'current.json'
                if key=='stock':
                    cmd=[a.engine,program,'bench',dst,'pooled']
                else:
                    w=a.out/'weights.json'
                    w.write_text(json.dumps(policies.get(key,{'weights':[0.]*9})['weights']))
                    cmd=[a.engine,program,'prefix-bench',dst,w]
                subprocess.run(cmd,check=True)
                v=READ(dst);assert (v['runs'],v['graph'])==(ref['pool']['runs'],ref['pool']['graph'])
                if trial:
                    row=rows[key]
                    for field in ('ms','maintenance_ms'):row.setdefault(field,[]).append(v[field])
                    if key!='stock':row.setdefault('choices',[]).append([v['offers'],v['selected']])
        for r in rows.values():
            r['median_ms']=median(r['ms']);r['median_maintenance_ms']=median(r['maintenance_ms'])
        summary[name]=rows
        print(name,[(k,round(v['median_ms'],2),round(v['median_maintenance_ms'],2)) for k,v in rows.items()],flush=True)
    (a.out/'timing.json').write_text(json.dumps(summary,indent=1)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','engine','episodes','out'):p.add_argument(k,type=Path)
    time(p.parse_args())
