"""Produce comparable counts and paired family-stratified deltas for Figure 20."""
import argparse
import csv
import json
from pathlib import Path
from statistics import median
import numpy as np

HERE=Path(__file__).resolve().parent
KEYS=("nonempty","nonempty_complete","wrong_parent","wrong_parent_same_eclass","absent_parent",
      "duplicates","missing","obligations","illegal","illegal_equality","early_local_equality",
      "uncommitted_local_equality","cross_instance_contamination","parent_ready","complete_when_ready",
      "secondary_correct","secondary_obligations","pending_claims","pending_conditional_requests",
      "active_outputs","unavailable_parent_obligations","outstanding_legal_obligations")


def tabulate(result,ts,group,label,arm):
    subset=[result["reports"][t['id']][arm]['groups'][group] for t in ts]
    row=dict(model=arm,subset=label,state=group,templates=len(ts),
             families=len({t['family_id'] for t in ts}))
    row.update({k:sum(v[k] for v in subset) for k in KEYS})
    for kind in ("all","different_origins","cross_owner","local_probe"):
        for k in ('tests','correct','false_positive','false_negative','positive'):
            row[f'{kind}_{k}']=sum(v['relation_'+kind][k] for v in subset)
    if group=='all':
        row['prepost_changed_requests']=sum(result['reports'][t['id']][arm]['switches']['changed'] for t in ts)
        row['prepost_both_correct']=sum(result['reports'][t['id']][arm]['switches']['both_correct'] for t in ts)
    else:row.update(prepost_changed_requests='NA',prepost_both_correct='NA')
    for lane in ('cached','cold'):
        if group=='all' and all(t['id'] in result['timings'] for t in ts):
            lanes=[result['timings'][t['id']][lane][arm] for t in ts]
            samples=[v for entry in lanes for v in entry['samples_ms']]
            row[lane+'_ms']=round(median(samples),4)
            row[lane+'_complete_per_second']=round(1000*sum(e['success'] for e in lanes)/sum(samples),3)
        else:row[lane+'_ms']=row[lane+'_complete_per_second']='NA'
    return row


def write(path,rows):
    with path.open('w') as f:
        w=csv.DictWriter(f,list(rows[0]),delimiter='\t',lineterminator='\n');w.writeheader();w.writerows(rows)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('report',type=Path);parser.add_argument('output',type=Path);a=parser.parse_args()
    result=json.loads(a.report.read_text());ts=json.loads((HERE/'corpus/manifest.json').read_text())['templates']
    held=[t for t in ts if t['split']=='heldout']
    groups=dict(heldout=held,train_family=[t for t in ts if t['split']=='train'])
    for t in held:groups[t['id']]=[t]
    for fam in {t['family_id'] for t in held}:groups[fam]=[t for t in held if t['family_id']==fam]
    rows=[tabulate(result,group,g,label,n) for label,group in groups.items() for n in result['fits']
          for g in result['reports'][group[0]['id']][n]['groups']]
    a.output.mkdir(parents=True,exist_ok=True);write(a.output/'metrics.tsv',rows)
    comparisons=[];rng=np.random.default_rng(63791)
    for seed in (1703,1709):
        for baseline,other in [('explicit','singleton'),('explicit','pairwise'),('singleton','incidence'),('pairwise','incidence')]:
            blocks=[]
            for t in held:
                data=result['reports'][t['id']]
                left=np.array(data[f'{baseline}-{seed}']['complete']);right=np.array(data[f'{other}-{seed}']['complete'])
                blocks.append((right-left).reshape(-1,8))
            raw=np.concatenate(blocks).ravel();draw=sum(b.sum(1)[rng.integers(len(b),size=(4000,len(b)))].sum(1) for b in blocks)
            lo,hi=np.percentile(draw,[2.5,97.5])
            comparisons.append(dict(seed=seed,baseline=baseline,comparison=other,gained=int(sum(raw>0)),lost=int(sum(raw<0)),
                delta=int(raw.sum()),group_bootstrap_low=round(float(lo),2),group_bootstrap_high=round(float(hi),2)))
    write(a.output/'paired.tsv',comparisons)
    for r in rows:
        if r['subset']=='heldout' and r['state']=='all':
            print(r['model'],*[r[k] for k in ('nonempty_complete','wrong_parent','duplicates','missing','all_correct','all_tests','cached_ms','cold_ms')])

if __name__=='__main__':main()
