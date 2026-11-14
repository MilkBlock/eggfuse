"""Audit GPU-generated Entry tuples against synthetic complete-match labels.

Pools are reconstructed from all captured candidates, never only positives.
This tests replacement of tuple enumeration on saved contexts, not Run execution.
"""
import argparse,hashlib,json
from pathlib import Path
import numpy as np
import mlx.core as mx
import mlx.nn as nn
from device_prefix_match import expand


def main():
    p=argparse.ArgumentParser();p.add_argument('dataset',type=Path);p.add_argument('weights',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--capacity',type=int,default=32);a=p.parse_args()
    manifest=json.loads(a.dataset.with_suffix('.json').read_text());meta=manifest['context_bank']
    fit=json.loads(a.weights.with_suffix('.json').read_text());digest=hashlib.sha256(a.dataset.read_bytes()).hexdigest()
    path=a.dataset.parent/meta['file']
    if digest!=manifest['dataset_sha256'] or digest!=fit['dataset_sha256'] or hashlib.sha256(path.read_bytes()).hexdigest()!=meta['sha256']:raise ValueError('data provenance mismatch')
    data=dict(np.load(a.dataset,allow_pickle=False));bank=dict(np.load(path,allow_pickle=False))
    model=nn.Sequential(nn.Linear(fit['input_width'],128),nn.GELU(),nn.Linear(128,128),nn.GELU(),nn.Linear(128,1));model.load_weights(str(a.weights))
    atoms=data['entry_records'].shape[1];ports=data['entry_roots'].shape[2];reports=[]
    for c,r in sorted(set(zip(data['case'].tolist(),data['rule'].tolist()))):
        ids=np.flatnonzero((data['case']==c)&(data['rule']==r));depth=int(np.sum(data['entry_records'][ids[0]]>=0));pools=[]
        for d in range(depth):
            items={}
            for i in ids:
                key=int(data['entry_sources'][i,d]),int(data['entry_records'][i,d]);value=data['entry_roots'][i,d]
                if key in items and not np.array_equal(items[key],value):raise ValueError('ambiguous Entry projection')
                items[key]=value
            keys=sorted(items);pools.append(dict(entries=mx.array(keys),roots=mx.array(np.array([items[k] for k in keys])),live=mx.ones(len(keys),mx.bool_)))
        context={k:mx.array(bank[f'case_{c}_{k}']) for k in ('roots','roles','mask','slot_valid')}
        out=expand(context,pools,mx.array(data['request'][ids[0]]),model,atoms,ports,a.capacity,mx);mx.eval(out)
        actual={tuple(map(tuple,row[:depth].tolist())) for row in np.array(out['entries'])[np.array(out['live'])]}
        expected={tuple((int(s),int(e)) for s,e in zip(data['entry_sources'][i,:depth],data['entry_records'][i,:depth])) for i in ids if data['valid'][i]>0}
        reports.append(dict(case=c,rule=r,expected=len(expected),generated=len(actual),missed=len(expected-actual),extra=len(actual-expected),
            complete=bool(out['complete']),overflow=bool(out['overflow']),active_choices=int(out['active_choices']),scheduled_choices=int(out['scheduled_choices']),
            captured_full_tuples=len(ids),passed=bool(out['complete']) and actual==expected))
    result=dict(scope='GPU prefix decoding on saved synthetic current contexts; pools from all captured candidates; no live Run integration',
        dataset_sha256=digest,weights_sha256=hashlib.sha256(a.weights.read_bytes()).hexdigest(),capacity=a.capacity,
        cases=len(reports),passed=sum(x['passed'] for x in reports),missed=sum(x['missed'] for x in reports),extra=sum(x['extra'] for x in reports),
        overflow=sum(x['overflow'] for x in reports),reports=reports)
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='reports'}))


if __name__=='__main__':main()
