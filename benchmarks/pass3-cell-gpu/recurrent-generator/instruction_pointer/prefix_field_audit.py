"""Count post-score shared-field conflicts over all typed choices on saved sealed snapshots."""
import argparse
from collections import Counter, defaultdict
import json
from multiprocessing import get_context
from pathlib import Path

import torch
from alternate_proofs import digest
from history import History
from prefix_policy import Policy, generate
from rule_read import load_actor


@torch.no_grad()
def audit(part):
    folder,weights,seed,low,high,k=part
    torch.set_num_threads(1)
    actor=load_actor(weights,True)
    cat=actor.catalog_type(json.loads((folder/'program.json').read_bytes()))
    history=History(cat,seed)
    nodes=actor.template_graph(cat)
    profile=defaultdict(Counter)
    issued={}
    with (folder/'memory.jsonl').open() as lines:
        for line in lines:
            snapshot=history.snapshot(json.loads(line))
            if snapshot.run>=low:
                mem=actor.memory(cat,snapshot,nodes)
                issued[snapshot.run]=sum(1 for _ in generate(actor,cat,mem,Policy(k),counts=profile,field_audit=True))
            if snapshot.run==high:
                break
    return issued,profile


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('root','weights','out'):p.add_argument(k,type=Path)
    p.add_argument('--case',required=True)
    p.add_argument('--workers',type=int,default=1)
    p.add_argument('--top-k',type=int,required=True)
    a=p.parse_args()
    folder=a.root/a.case
    runs=json.loads((folder/'capture.json').read_bytes())['runs']
    if not 1<=a.workers<=runs:p.error('workers outside Run range')
    seed={r['directory']:r['seed'] for r in json.loads((a.root/'manifest.json').read_bytes())}.get(a.case,0)
    parts=[(folder,a.weights,1703+seed,runs*i//a.workers+1,runs*(i+1)//a.workers,a.top_k) for i in range(a.workers)]
    with get_context('spawn').Pool(a.workers) as pool:
        results=pool.map(audit,parts)
    counts=defaultdict(Counter)
    by_run={}
    for records,profile in results:
        if by_run.keys() & records.keys():raise ValueError('overlapping source runs')
        by_run.update(records)
        for k,v in profile.items():counts[k].update(v)
    if len(by_run)!=runs:raise ValueError('incomplete source runs')
    a.out.write_text(json.dumps(dict(case=a.case,weights_sha256=digest(a.weights),cap=a.top_k,issued_by_run=by_run,
        layers={f'{kind}_{depth}':dict(c) for (kind,depth),c in counts.items()}),indent=2)+'\n')
