"""Choose issuance thresholds on reserved training-program Runs using distinct native commits."""
import argparse
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path

import torch

from anchor_set_audit import check
from entry_coverage import split_runs
from history import History
from rule_read import load_actor


def read(p):return json.loads(p.read_bytes())
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()


@torch.no_grad()
def calibrate(root,receiver,initial,out,seed):
    torch.set_num_threads(1)
    model=load_actor(initial,True)
    original=model.thresholds.tolist()
    selected,_,reserved=split_runs(root,seed)
    snapshots=[]
    references={}
    required=0
    for record,_ in selected:
        name=record['directory']
        runs={r for n,r in reserved if n==name}
        if not runs:continue
        folder=root/name
        program=read(folder/'program.json')
        cat=model.catalog_type(program)
        tape=read(folder/'tape.json')
        references[name]=tape
        required+=sum(p['run'] in runs for p in tape['requests'])
        history=History(cat,seed+record['seed'])
        nodes=model.template_graph(cat)
        with (folder/'memory.jsonl').open() as source:
            for line in source:
                raw=json.loads(line)
                s=history.snapshot(raw,raw['run'] in runs)
                if s is None:continue
                mem=model.memory(cat,s,nodes)
                address={p.address:(history.inverse[p.address[0]],p.version) for p in s.ports}
                snapshots.append((name,cat,s.run,mem,address))
    if len(snapshots)!=len(reserved) or not required:raise ValueError('incomplete calibration split')
    # The first policy establishes a small paid lower bound by emitting eligible
    # zero-parent rules alone. Negative and positive logit cuts are fixed up front.
    grid=[(float('inf'),float('inf')),(original[1],original[2])]
    grid+= [(a,b) for a in (2.,1.,0.,-1.,original[1]) for b in (1.,0.,-1.,original[2])]
    records=[]
    best=None
    best_f1=-1.
    for root_cut,parent_cut in dict.fromkeys(grid):
        model.thresholds[1]=root_cut
        model.thresholds[2]=parent_cut
        packets=defaultdict(list)
        paid=0
        eliminated=False
        for name,cat,run,mem,address in snapshots:
            for rid,refs in model.generate(cat,mem):
                paid+=1
                # Even recovering ALL reference commits cannot beat the incumbent
                # beyond this point. No partial run is scored as a finished policy.
                if 2*required/(required+max(required,paid))<best_f1:
                    eliminated=True
                    break
                parents=[]
                for alias,op in refs:
                    token,version=address[alias,op]
                    parents.append(dict(address=dict(token=token,op=op),version=version))
                items=packets[name]
                items.append(dict(token=len(items)+1,run=run,rule=rid,parents=parents))
            if eliminated:break
        spec=dict(root=root_cut if root_cut!=float('inf') else None,
                  parent=parent_cut if parent_cut!=float('inf') else None,observed_issues=paid)
        if eliminated:
            records.append(dict(**spec,pruned=True,f1_upper=2*required/(required+max(required,paid))))
            continue
        results=Counter()
        for name,items in packets.items():
            a=check(root/name,receiver,references[name],items)
            hits=set()
            for run,t,w,reason in a['recall_verdicts']:
                if items[t-1]['run']!=run:raise ValueError('inconsistent calibration receipt')
                if w is not None:
                    if (run,w) in hits:results['duplicates']+=1
                    hits.add((run,w))
                else:results[reason]+=1
            results['recovered']+=len(hits)
        f1=2*results['recovered']/(required+paid)
        records.append(dict(**spec,pruned=False,f1=f1,counts=dict(results)))
        if f1>best_f1:
            best_f1=f1
            best=(root_cut,parent_cut)
    if best is None or not best_f1>0:raise ValueError('no verified calibration coverage')
    model.thresholds[1]=best[0]
    model.thresholds[2]=best[1]
    state=torch.load(initial,weights_only=True,map_location='cpu')
    for k,v in model.state_dict().items():
        if k!='thresholds' and not torch.equal(v,state['parameters'][k]):raise ValueError('weights changed')
    state['parameters']=model.state_dict()
    out.mkdir(exist_ok=True,parents=True)
    torch.save(state,out/'model.pt')
    (out/'calibration.json').write_text(json.dumps(dict(mode='shadow calibration',initial_sha256=digest(initial),
        weights_sha256=digest(out/'model.pt'),receiver_sha256=digest(receiver),runs=len(snapshots),
        required=required,original=original,chosen=[None if v==float('inf') else v for v in model.thresholds.tolist()],
        best_f1=best_f1,grid=records),indent=2)+'\n')
    print(required,best,best_f1,len(records),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('root','receiver','initial','out'):p.add_argument(k,type=Path)
    p.add_argument('--seed',type=int,default=1703)
    a=p.parse_args();calibrate(a.root,a.receiver,a.initial,a.out,a.seed)
