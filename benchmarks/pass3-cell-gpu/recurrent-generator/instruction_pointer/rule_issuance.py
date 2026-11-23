"""Measure rule/Run activation before parent completion on the full sealed teacher schedule."""
import argparse
from collections import Counter,defaultdict
from multiprocessing import get_context
import json
from pathlib import Path

import torch
from alternate_proofs import addr,digest
from anchor_set import Domains
from history import History
from prefix_policy import Policy,select_frontier
from rule_read import load_actor


@torch.no_grad()
def scan(job):
    folder,weight_paths,seed,lo,hi=job
    torch.set_num_threads(1)
    models=[load_actor(p,True) for p in weight_paths]
    # Field tensors contribute only to later parent comparisons. Root scores
    # require the same full port keys as production.
    for model in models:model.field_pointer=False
    program=json.loads((folder/'program.json').read_bytes())
    cats=[m.catalog_type(program) for m in models]
    nodes=[m.template_graph(c) for m,c in zip(models,cats)]
    hist=History(cats[0],seed)
    tape=defaultdict(list)
    for r in json.loads((folder/'tape.json').read_bytes())['requests']:
        if lo<=r['run']<=hi:tape[r['run']].append(r)
    totals=[Counter() for _ in models]
    for line in (folder/'memory.jsonl').open():
        raw=json.loads(line)
        s=hist.snapshot(raw)
        if s.run<lo:continue
        teacher=tape[s.run]
        correct={r['rule'] for r in teacher}
        for m,c,n,total in zip(models,cats,nodes,totals):
            mem=m.memory(c,s,n)
            dom=Domains(mem)
            active=set()
            chosen=set()
            for rid,wm in mem.rules.items():
                atoms=c.atoms[rid]
                if not atoms:
                    if ((not c.seminaive[rid] or wm==0)
                            and m.root_scores(c,mem,rid,None,None,dom).item()>=m.thresholds[0]):
                        active.add(rid)
                    continue
                for anchor in range(len(atoms) if c.seminaive[rid] else 1):
                    order=[anchor]+[i for i in range(len(atoms)) if i!=anchor]
                    ids=select_frontier(m,c,mem,dom,rid,anchor,order,0,dom.empty.reshape(1,0),
                                        Policy(32),None,Counter(),False)
                    if len(ids):
                        active.add(rid)
                        chosen.update((rid,anchor,s.ports[j].address) for j in ids[:,0].tolist())
            total.update(runs=1,required_rule_runs=len(correct),fired_rule_runs=len(active),
                         correct_rule_runs=len(active&correct),required_commits=len(teacher))
            for request in teacher:
                rid=request['rule']
                if rid in active:
                    total['commits_with_active_rule']+=1
                parents=request['parents']
                if parents:
                    i=next(i for i,v in enumerate(parents) if not c.seminaive[rid] or v['version']>=s.rules[rid])
                    eligible=(rid,i,hist.rename(addr(parents[i]['address']))) in chosen
                else:
                    eligible=rid in active
                total['commits_with_teacher_anchor']+=int(eligible)
        if s.run==hi:break
    return totals


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('root','out'):parser.add_argument(key,type=Path)
    parser.add_argument('--case',required=True)
    parser.add_argument('--weights',nargs='+',required=True,type=Path)
    parser.add_argument('--workers',type=int,default=1)
    a=parser.parse_args()
    folder=a.root/a.case
    runs=json.loads((folder/'capture.json').read_bytes())['runs']
    if not 1<=a.workers<=runs:parser.error('invalid number of workers')
    seed={r['directory']:r['seed'] for r in json.loads((a.root/'manifest.json').read_bytes())}.get(a.case,0)
    jobs=[(folder,a.weights,1703+seed,runs*i//a.workers+1,runs*(i+1)//a.workers) for i in range(a.workers)]
    with get_context('spawn').Pool(a.workers) as pool:
        partitions=pool.map(scan,jobs)
    result=[sum((s[j] for s in partitions),Counter()) for j in range(len(a.weights))]
    if any(r['runs']!=runs for r in result):
        raise ValueError('incomplete source schedule')
    a.out.write_text(json.dumps(dict(case=a.case,mode='pre-completion rule activation',
        weights=[digest(p) for p in a.weights],counts=result),indent=2)+'\n')
