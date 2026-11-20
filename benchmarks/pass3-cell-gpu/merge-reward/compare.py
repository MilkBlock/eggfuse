"""Summarize paired interventions. Identical native gate decisions are one behavioral outcome."""
import json
from pathlib import Path
from statistics import median


def summarize(results):
    names=set.intersection(*(set(v) for v in results.values()))
    examples={}
    for name in sorted(names):
        if name=='vanilla':continue
        r=[x[name] for x in results.values()]
        examples[name]=dict(offers=sum(x['selected'] for x in r),completed=sum(x['completed'] for x in r),
            work=sum(x['net_operations'] for x in r),
            median_time_ratio_to_leaf=median(v[name]['median_ms']/v['leaf']['median_ms'] for v in results.values()))
    same={}
    for r in ('prior','offer','settled','work','charged'):
        if 'real-'+r not in names or 'synthetic-'+r not in names:continue
        changed=[]
        for case,v in results.items():
            a,b=v['real-'+r],v['synthetic-'+r]
            if a['decisions']==b['decisions']:
                assert (a['selected'],a['completed'],a['net_operations'])==(b['selected'],b['completed'],b['net_operations'])
            else:changed.append(case)
        same[r]=dict(same=len(results)-len(changed),changed=changed)
    return dict(groups=len(results),arms=examples,comparison=same)


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('results',type=Path);p.add_argument('out',type=Path)
    a=p.parse_args();a.out.write_text(json.dumps(summarize(json.loads(a.results.read_bytes())),indent=1)+'\n')
