"""Deploy frozen gate checkpoints at the real Cell boundary, with two paired execution controls."""
import argparse
import json
from pathlib import Path
from statistics import median
import numpy as np
from native import EVAL, digest, session, save


def summarize(item, policy):
    charges=item['charges'];boundary=item['boundary']
    selected=[r for r in charges if r['selected']]
    margin=None
    if policy is not None:
        x=np.asarray([r['features'] for r in charges],dtype=np.float32)
        score=np.full(len(x),policy['bias'],dtype=np.float32)
        for col,w in enumerate(policy['weights']):
            score+=x[:,col]*np.float32(w)
        margin=float(np.abs(score-np.float32(policy['threshold'])).min()) if len(score) else None
        assert np.array_equal(score>=np.float32(policy['threshold']),[r['selected'] for r in charges])
    unique={r['generation'] for r in charges}
    assert len(unique)==len(charges) and sum(r['counts'][2] for r in charges)==item['children']
    assert boundary[2]-boundary[3] == sum(r['counts'][0]-r['counts'][1] for r in selected)
    # Three measured kinds of operations: entry visits, repeated root seals, independent child packets.
    # Work counts are not nanoseconds and do not imply that a source-visible node was retired.
    return dict(delta_maintenance=item.get('delta'),min_decision_margin=margin,
                skipped_on_nonwinners=sum(r['counts'][0]-r['counts'][1] for r in selected if not r['counts'][2]),
                opportunities=len(charges),selected=len(selected),completed=sum(r['counts'][2] for r in selected),
                verified_child_total=item['children'],skipped_entries=boundary[2]-boundary[3],
                header_scans=boundary[1],saved_seals=boundary[6],saved_fields=boundary[7],saved_packets=boundary[8],
                net_operations=boundary[2]-boundary[3]-boundary[1]+boundary[6]+boundary[8],
                decisions=digest([r['generation'] for r in selected]),rhs=item['rhs'],direct=item['direct'],fresh=item['fresh'],
                endpoint_digest=digest(item['endpoints']),runs=item['runs'],chain=item['chain'],ms=[])


def main(a):
    a.out.mkdir(parents=True,exist_ok=False)
    collection=json.loads(a.policies.read_bytes());result={}
    for case in a.cases:
        for seed in a.seeds:
            arms={'leaf':(0,None),'all':(a.mode,None)}
            for key,v in collection['policies'].items():
                arm=key.partition('-')[2]
                if key.startswith(f'{seed}-') and (not a.arms or arm in a.arms):arms[arm]=(a.mode,v['gate'])
            trials={}
            with session(a.exp,a.binary,case,seed,a.out) as run:
                for n,(mode,policy) in arms.items():
                    item=run(policy,True,mode);trials[n]=summarize(item,policy)
                    if n=='leaf':gold=item['endpoints']
                    else:assert item['endpoints']==gold,(case,seed,n)
                names=list(arms)
                for lap in range(1+a.repeats):
                    offset=(lap*5)%len(names);order=names[offset:]+names[:offset]
                    for n in order if lap%2==0 else reversed(order):
                        mode,policy=arms[n];ms,state,steps=run(policy,False,mode)
                        assert state==gold['state'] and steps==trials[n]['runs']
                        if lap:trials[n]['ms'].append(ms)
                for arm in trials.values():arm['median_ms']=median(arm['ms'])
            result[f'{case}/{seed}']=trials;save(a.out/'results.json',result)
            print(case,seed,[(n,v['selected'],v['completed'],v['net_operations'],round(v['median_ms'],1)) for n,v in trials.items()],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','binary','policies','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',choices=EVAL,default=EVAL);p.add_argument('--seeds',type=int,nargs='+',default=[1703,1709])
    p.add_argument('--arms',nargs='+');p.add_argument('--mode',type=int,choices=(3,4),default=3)
    p.add_argument('--repeats',type=int,default=6);main(p.parse_args())
