"""Validate the receipt partition and compare budgeted recovery with the frozen root policy."""
import argparse
import csv
import json
from pathlib import Path

from higher_cell import read
from layout_credit_report import verify


def report(baseline,experiment,gold,out):
    out.mkdir(parents=True,exist_ok=True)
    summary={}
    audits={}
    exclusive={}
    controls={}
    with (out/'run-recall.csv').open('w',newline='') as stream:
        writer=csv.writer(stream,lineterminator='\n')
        writer.writerow(['mode','program','run','signed','reference'])
        for arm in ('baseline','learned','margin'):
            folder=baseline/'recall/readable' if arm=='baseline' else experiment/'assist'/arm
            trajectory=baseline/'exclusive/readable' if arm=='baseline' else experiment/'exclusive'/arm
            audits[arm]={};summary[arm]={};exclusive[arm]={}
            for path in sorted(folder.glob('*.json')):
                data=read(path)
                run=data['execution']
                name=data['program']
                verify(data,read(gold/(name+'.json')))
                control=tuple(data[k] for k in ('actor','catalog','reader','scorer','policy','tape','binary'))
                if controls.setdefault(name,control)!=control:
                    raise ValueError('mismatched experiment inputs')
                steps=data.pop('recall_by_nonempty_run')
                n=run['counts']['accepted']
                if sum(a for _,a,_ in steps)!=n or sum(b for _,_,b in steps)!=data['reference_commits']:
                    raise ValueError('receipt totals differ')
                for r,a,b in steps:writer.writerow((arm,name,r,a,b))
                ops=sum(run['ept']['signed_external']+run['ept']['signed_internal'])
                audits[arm][name]=data
                exc=read(trajectory/path.name)
                if exc['independent_search_calls']!=0:raise ValueError('exclusive search enabled')
                exclusive[arm][name]=exc
                summary[arm][name]=dict(signed=n,required=data['reference_commits'],paid=run['issued'],
                    operations=ops,ept=ops/run['issued'],recall=n/data['reference_commits'],
                    complete=sum(a==b for _,a,b in steps),nonempty=len(steps),equal_prefix=exc['common_runs'],
                    final_equal=exc['final_equal'],panic=exc['failure'])
    if not controls or any(c.keys()!=controls.keys() for c in summary.values()):
        raise ValueError('incomplete comparison')
    for name,value in [('summary',summary),('assist',audits),('exclusive',exclusive)]:
        (out/(name+'.json')).write_text(json.dumps(value,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('baseline','experiment','gold','out'):p.add_argument(k,type=Path)
    a=p.parse_args()
    report(a.baseline,a.experiment,a.gold,a.out)
