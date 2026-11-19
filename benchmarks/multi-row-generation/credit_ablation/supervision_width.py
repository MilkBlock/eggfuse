"""Post-hoc matched-training-length check: additional SFT at one versus two rows."""
import argparse
import json
from pathlib import Path
from statistics import median
import numpy as np
import torch

from evaluate import draw_timing, timing_ids
from credit_inputs import templates, fresh_panel, SEEDS
from model import WidthSystem
from fit import device, digest, transfer, EClassSchema
from audit import metrics
from evaluate_width import check_trace, host, merge


def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);a=p.parse_args()
    dev=device();ts=templates();schema=EClassSchema([t for t in ts if t['split']=='train'])
    models={};metadata={};results={};times={}
    for seed in SEEDS:
        group=[]
        for suffix in ('supervised1','supervised'):
            folder=a.root/f'{suffix}-{seed}';info=json.loads((folder/'fit.json').read_text())
            assert info['model_sha256']==digest(folder/'final.pt')
            group.append((info['parent_sha256'],info['steps'],info['data_order'],info['actor_lr'],info['batch'],info['test_manifest_sha256']))
            m=WidthSystem(schema,seed);m.load_state_dict(torch.load(folder/'final.pt',map_location='cpu',weights_only=True));m.to(dev).eval()
            for rows in (1,2):
                key=f'{suffix}-{seed}-eval{rows}'
                models[key]=m,rows;metadata[key]=info['model_sha256']
        assert group[0]==group[1]
    with torch.inference_mode():
        for index,t in enumerate(x for x in ts if x['split']=='heldout'):
            tid=t['id'];d=fresh_panel(t);bank=schema.bank(t,'pairwise',dev)
            tables={n:m.encoder.frozen_bank(bank) for n,(m,rows) in models.items()};bulk={};results[tid]={}
            for n,(m,rows) in models.items():
                st,tok,rel=merge([host(m(*transfer(d,slice(i,i+64),dev),tables[n],rows=rows)) for i in range(0,len(d['a']),64)])
                check_trace(d,st,tok);r=metrics(d,*st,rows,rel)
                results[tid][n]={k:v for k,v in r['run2'].items() if k!='per_graph'};bulk[n]=st
            times[tid]=draw_timing(models,d,tables,bulk,timing_ids(d,index),dev,index)
    stats={}
    for n in models:
        parts=[p[n] for p in results.values()];lanes=[p[n] for p in times.values()];samples=[v for group in lanes for v in group['samples_ms']]
        stats[n]=dict(complete=sum(p['nonempty_complete_graphs'] for p in parts),graphs=sum(p['nonempty_graphs'] for p in parts),
                      missing=sum(p['missing'] for p in parts),duplicates=sum(p['duplicates'] for p in parts),
                      timed_correct=sum(p['complete'] for p in lanes),median_ms=median(samples),valid_per_s=1000*sum(p['complete'] for p in lanes)/sum(samples))
    (a.root/'supervision-width.json').write_text(json.dumps(dict(stats=stats,panels=results,timings=times,weight_sha256=metadata),indent=2)+'\n')
    print(stats)

if __name__=='__main__':main()
