"""Time CPU neural anchor selection on the sealed token memory of each source Run."""
import argparse
import json
from pathlib import Path
from time import perf_counter_ns

import torch

from alternate_proofs import digest
from anchor_set import Domains
from higher_cell import read
from history import History
from prefix_policy import Policy
from prefix_recovery import Recovery,select
from collections import Counter
from rule_read import load_actor


@torch.no_grad()
def measure(folder,weights,head,seed,save_choices=False):
    model=load_actor(weights,True)
    start=perf_counter_ns()
    cat=model.catalog_type(read(folder/'program.json'))
    nodes=model.template_graph(cat)
    template_ns=perf_counter_ns()-start
    history=History(cat,seed)
    policy=Policy(32,recovery=Recovery(head,weights))
    rows=[]; choices=[]; encode_ns=0; history_ns=0; selector_ns=0
    with (folder/'memory.jsonl').open() as stream:
        for line in stream:
            frame=json.loads(line)
            start=perf_counter_ns()
            snap=history.snapshot(frame)
            history_ns+=perf_counter_ns()-start
            start=perf_counter_ns()
            mem=model.memory(cat,snap,nodes)
            domains=Domains(mem)
            encode_ns+=perf_counter_ns()-start
            for rule in snap.rules:
                atoms=cat.atoms[rule]
                for role in range(len(atoms) if cat.seminaive[rule] else min(1,len(atoms))):
                    domain=domains.role(cat,mem,rule,role,role)
                    if not len(domain):
                        rows.append([snap.run,rule,role,0,0,0,0])
                        continue
                    start=perf_counter_ns()
                    score=model.root_scores(cat,mem,rule,role,domain,domains)
                    ns=perf_counter_ns()-start
                    if score.numel()!=len(domain):
                        raise ValueError('anchor scoring omitted a port')
                    order=cat.read_order(rule,role,'source')
                    start=perf_counter_ns()
                    retained=select(model,cat,mem,domains,rule,role,order,0,domains.empty.reshape(1,0),policy,Counter()).flatten()
                    whole=perf_counter_ns()-start
                    selector_ns+=whole
                    rows.append([snap.run,rule,role,len(domain),len(retained),ns,whole])
                    if save_choices:
                        for j in retained.tolist():
                            port=mem.ports[j]; alias,op=port.address
                            choices.append([snap.run,rule,role,history.inverse[alias],op,port.version])
    return dict(mode='CPU on recorded teacher snapshots',actor=digest(weights),program=digest(folder/'program.json'),
                recovery=policy.recovery.checkpoint,seed=seed,runs=history.run,template_ns=template_ns,
                history_ns=history_ns,encode_ns=encode_ns,selector_ns=selector_ns,rows=rows),choices


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('folder','weights','recovery','output'):p.add_argument(k,type=Path)
    p.add_argument('--seed',type=int,default=3434)
    p.add_argument('--choices',type=Path)
    a=p.parse_args()
    torch.set_num_threads(1)
    result,choices=measure(a.folder,a.weights,a.recovery,a.seed,a.choices is not None)
    a.output.write_text(json.dumps(result)+'\n')
    if a.choices:a.choices.write_text(json.dumps(choices)+'\n')
