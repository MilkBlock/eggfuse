"""Tabulate paired graph coverage and actual valid throughput on the fresh panel."""
import argparse
import csv
import json
from pathlib import Path
from statistics import median

import numpy as np


def totals(record_list):
    keys=record_list[0]
    return {k:sum(int(v[k]) for v in record_list) for k in keys if isinstance(record_list[0][k],(int,bool))}


def tsv(path,rows):
    with path.open('w') as f:
        writer=csv.DictWriter(f,list(rows[0]),delimiter='\t',lineterminator='\n')
        writer.writeheader();writer.writerows(rows)


def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('out',type=Path);a=p.parse_args()
    result=json.loads((a.root/'results.json').read_text());templates=list(result['panels'])
    a.out.mkdir(exist_ok=True,parents=True);rows=[];pair=[]
    for sub,ts in [('all',templates)]+[(t,[t]) for t in templates]:
        for name in result['panels'][ts[0]]:
            r2=totals([result['panels'][t][name]['r2'] for t in ts])
            r1=totals([result['panels'][t][name]['r1'] for t in ts])
            timing=[result['timings'][t][name] for t in ts if name in result['timings'][t]]
            samples=[x for d in timing for x in d['samples_ms']]
            successes=sum(v['complete'] for v in timing)
            rows.append(dict(subset=sub,case=name,run1_complete=r1['complete_graphs'],**r2,
                median_ms=round(median(samples),4) if samples else 'NA',timed_success=successes if samples else 'NA',
                timed_graphs=len(samples) if samples else 'NA',correct_graphs_per_second=round(1000*successes/sum(samples),3) if samples else 'NA'))
            bucket=[result['paired'][t][name]['common_parent_ready_nonempty'] for t in ts]
            by_group=[torchfree['nonempty'] for t in ts for torchfree in result['paired'][t][name]['per_group'].values()]
            delta=np.array([g['candidate_only']-g['baseline_only'] for g in by_group]).reshape(len(ts),-1)
            rng=np.random.default_rng(36631)
            repeats=sum(v[rng.integers(len(v),size=(4096,len(v)))].sum(1) for v in delta)
            lo,hi=np.percentile(repeats,[2.5,97.5])
            pair.append(dict(subset=sub,case=name,net_delta=int(delta.sum()),
                         interval_low=round(float(lo),2),interval_high=round(float(hi),2),**totals(bucket)))
    tsv(a.out/'metrics.tsv',rows);tsv(a.out/'paired.tsv',pair)

if __name__=='__main__':main()
