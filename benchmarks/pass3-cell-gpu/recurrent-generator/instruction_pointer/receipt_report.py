"""Compare shared layout policies under the same root generator and native contract."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path

from higher_cell import read
from layout_credit_report import verify


def summarize(experiment, gold, out, cases):
    out.mkdir(parents=True, exist_ok=True)
    summary, audits, exclusive, controls = {}, {}, {}, {}
    with (out/'run-recall.csv').open('w', newline='') as stream:
        writer = csv.writer(stream, lineterminator='\n')
        writer.writerow(['arm','program','run','signed','reference'])
        for arm in ('baseline','learned','commits'):
            audits[arm], exclusive[arm], summary[arm] = {}, {}, {}
            total = Counter()
            for name in cases:
                audit = read(experiment/arm/(name+'.json'))
                verify(audit, read(gold/(name+'.json')))
                settings = {k:audit[k] for k in ('binary','actor','catalog','reader','scorer','recovery',
                                                    'tape','omit','attach','seed')}
                if controls.setdefault(name,settings) != settings:
                    raise ValueError('root generator, layout budget or native receiver changed')
                run, credit = audit['execution'], audit['credit']
                steps = run['layouts']['counts']
                if arm != 'baseline' and not credit.get('receipt_value_decisions'):
                    raise ValueError('receipt policy did not run')
                rows = audit.pop('recall_by_nonempty_run')
                if (sum(n for _,n,_ in rows) != run['counts']['accepted'] or
                        sum(n for _,_,n in rows) != audit['reference_commits']):
                    raise ValueError('per-Run receipt totals differ')
                writer.writerows((arm,name,*row) for row in rows)
                trajectory = read(experiment/'exclusive'/arm/(name+'.json'))
                if trajectory['independent_search_calls'] != 0:
                    raise ValueError('exclusive used search')
                exclusive[arm][name] = trajectory
                audits[arm][name] = audit
                s = dict(signed=run['counts']['accepted'], required=audit['reference_commits'],
                         paid=run['issued'], ops=sum(run['ept']['signed_external']+run['ept']['signed_internal']),
                         owned=credit.get('owned_valid',0), uncontested_effects=credit.get('uncontested_effects',0),
                         failed_steps=credit.get('failed_steps',0), held_complete=audit['held_complete'],
                         large_complete=sum(v for size,v in steps['completed_sizes'].items() if int(size)>=6),
                         complete_runs=sum(a==b for _,a,b in rows))
                summary[arm][name] = s
                total.update(s)
            summary[arm]['total'] = dict(total,ept=total['ops']/total['paid'],
                                         coverage=total['signed']/total['required'])
    for file, data in [('summary',summary),('assist',audits),('exclusive',exclusive)]:
        (out/(file+'.json')).write_text(json.dumps(data,indent=2)+'\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for k in ('experiment','gold','out'):
        p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',required=True)
    a = p.parse_args()
    summarize(a.experiment,a.gold,a.out,a.cases)
