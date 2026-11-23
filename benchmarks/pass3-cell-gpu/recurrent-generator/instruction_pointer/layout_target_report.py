"""Check the three selectors against the same source ledgers and report complete nonempty Runs."""
import argparse
import csv
import json
from pathlib import Path
from statistics import mean

from higher_cell import read
from layout_credit_report import verify


def summarize(experiment,gold,outputs):
    outputs.mkdir(parents=True,exist_ok=True)
    summary={}
    audits={}
    with (outputs/'run-recall.csv').open('w',newline='') as stream:
        writer=csv.writer(stream,lineterminator="\n")
        writer.writerow(['selector','workload','run','signed_commits','teacher_commits'])
        for folder in sorted((experiment/'recall').iterdir()):
            records={}
            audits[folder.name]={}
            for path in sorted(folder.glob('*.json')):
                raw=read(path)
                verify(raw,read(gold/(path.stem+'.json')))
                rows=raw.pop('recall_by_nonempty_run')
                run=raw['execution']
                if (sum(a for _,a,_ in rows)!=run['counts']['accepted'] or
                    sum(b for _,_,b in rows)!=raw['reference_commits'] or
                    any(not 0<=a<=b or not b for _,a,b in rows)):
                    raise ValueError('invalid per-Run attribution')
                for r,a,b in rows:
                    writer.writerow((folder.name,path.stem,r,a,b))
                paid=run['issued']
                ops=sum(run['ept']['signed_external']+run['ept']['signed_internal'])
                records[path.stem]=dict(paid=paid,ops=ops,ept=ops/paid,teacher=raw['reference_commits'],
                    signed=run['counts']['accepted'],nonempty=len(rows),complete=sum(a==b for _,a,b in rows),
                    mean_recall=mean(a/b for _,a,b in rows),held_complete=raw['held_complete'],
                    uncredited=run['assist']['residual_commits'])
                audits[folder.name][path.stem]=raw
            summary[folder.name]=records
    if set(summary)!={'bandit','observed','readable','static'} or not all(summary.values()):
        raise ValueError('missing selector experiments')
    if len({tuple(sorted(cases)) for cases in summary.values()})!=1:
        raise ValueError('selector workload sets differ')
    for workload in summary['bandit']:
        controls={tuple(a[workload][k] for k in ('tape','binary','actor','catalog','reader','scorer'))
                  for a in audits.values()}
        if len(controls)!=1:
            raise ValueError('selector arms use different data or frozen components')
    for filename,data in [('summary.json',summary),('assist.json',audits)]:
        (outputs/filename).write_text(json.dumps(data,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('experiment','gold','out'):
        p.add_argument(k,type=Path)
    a=p.parse_args()
    summarize(a.experiment,a.gold,a.out)
