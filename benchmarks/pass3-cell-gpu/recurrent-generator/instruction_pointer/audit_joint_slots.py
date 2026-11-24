"""Shadow complete, simultaneous Cell requests on held sealed snapshots."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
from time import perf_counter

import torch

from alternate_proofs import digest
from anchor_set import Domains
from anchor_set_audit import check
from history import History,address
from joint_slots import JointSlots, named_requests, rule_inputs
from rule_read import load_actor


@torch.no_grad()
def audit(folder, weights, model_dir, receiver):
    start=perf_counter()
    raw=json.loads((folder/'program.json').read_bytes())
    tape=json.loads((folder/'tape.json').read_bytes())
    config=json.loads((model_dir/'training.json').read_bytes())
    if config['base']!=digest(weights) or config['head']!=digest(model_dir/'head.pt'):
        raise ValueError('checkpoint mismatch')
    actor=load_actor(weights,True)
    head=JointSlots(actor.width,config['proposals']).eval()
    head.load_state_dict(torch.load(model_dir/'head.pt',map_location='cpu',weights_only=True))
    cat=actor.catalog_type(raw)
    nodes=actor.template_graph(cat)
    history=History(cat,3434,cache_ports=True)
    requests=[]
    work=Counter()
    with (folder/'memory.jsonl').open() as stream:
        for line in stream:
            snap=history.snapshot(json.loads(line))
            mem=actor.memory(cat,snap,nodes)
            dom=Domains(mem)
            for rid in snap.rules:
                prepared=rule_inputs(cat,mem,dom,rid)
                if prepared is None: continue
                inputs,ids=prepared
                scores,stop=head(*inputs,config['rounds'])
                work['rule_calls']+=1
                work['proposal_slots']+=len(stop)
                work['pointer_scores']+=sum(s.numel() for s in scores)*(1+config['rounds'])
                for req in named_requests(rid,history,mem,ids,scores,stop):
                    req['token']=len(requests)+1
                    requests.append(req)
    neural=perf_counter()-start
    report=check(folder,receiver,tape,requests)
    by_run=defaultdict(set)
    hits=set()
    approved=0
    rejects=Counter()
    for run,_,winner,reason in report['recall_verdicts']:
        if winner is None:
            rejects[reason]+=1
        else:
            hits.add(winner);by_run[run].add(winner);approved+=1
    targets=defaultdict(list)
    required=Counter()
    for q in tape['requests']:
        targets[q['run'],q['rule']].append(q)
        required[q['run']]+=1
    pairs=Counter()
    for qs in targets.values():
        if len(qs)!=2 or any(len(q['parents'])!=2 for q in qs):continue
        if any(address(qs[0]['parents'][i]['address'])==address(qs[1]['parents'][i]['address']) for i in range(2)):continue
        pairs[sum(q['token'] in hits for q in qs)]+=1
    return dict(mode='shadow',work=work,source_runs=history.run,head=config['head'],receiver=digest(receiver),
                required=sum(required.values()),distinct=len(hits),paid=len(requests),duplicates=approved-len(hits),
                rejected=rejects,paired_binary_groups=dict(pairs),network_seconds=neural,
                native_audit_wall_seconds=perf_counter()-start-neural,
                per_run=[[r,required[r],len(by_run[r])] for r in range(1,history.run+1)])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('folder','weights','model_dir','receiver','output'):p.add_argument(key,type=Path)
    a=p.parse_args()
    torch.set_num_threads(1)
    a.output.write_text(json.dumps(audit(a.folder,a.weights,a.model_dir,a.receiver),indent=2)+'\n')
