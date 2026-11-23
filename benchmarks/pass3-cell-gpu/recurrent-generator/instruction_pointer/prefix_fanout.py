"""Recount accepted prefix branches in a sealed Run, without materializing final packets."""
import argparse
from collections import Counter
import json
from pathlib import Path

import torch
from anchor_set import Domains
from alternate_proofs import digest
from history import stream
from rule_read import load_actor


@torch.no_grad()
def profile(model,folder,run,seed):
    cat,s=next(stream(folder,seed,{run},model.catalog_type))
    mem=model.memory(cat,s)
    dom=Domains(mem)
    report=[]
    zero=0
    for rid,wm in s.rules.items():
        atoms=cat.atoms[rid]
        if not atoms:
            if not cat.seminaive[rid] or wm==0:
                zero+=int(model.root_scores(cat,mem,rid,None,None,dom).item()>=model.thresholds[0])
            continue
        for a in range(len(atoms) if cat.seminaive[rid] else 1):
            ids=dom.role(cat,mem,rid,a,a)
            if not len(ids):continue
            root=model.root_scores(cat,mem,rid,a,ids,dom)>=model.thresholds[1]
            first=ids[root]
            if not len(first):continue
            order=[a]+[j for j in range(len(atoms)) if j!=a]
            widths=[len(first)]+[0]*(len(atoms)-1)
            disagree=[0]*len(order)
            def extend(k,prefix):
                if k==len(order):return
                role=order[k]
                ports=dom.role(cat,mem,rid,a,role)
                if not len(ports):return
                for batch in prefix.split(max(1,65536//len(ports))):
                    scores=model.pair_scores(cat,mem,rid,order[:k],batch,role,ports)
                    row,col=(scores>=model.thresholds[2]).nonzero(as_tuple=True)
                    widths[k]+=len(row)
                    # Diagnostic only, after acceptance, never filters the pointer.
                    different=torch.zeros(len(row),dtype=torch.bool)
                    for j,earlier in enumerate(order[:k]):
                        for src,dst in cat.field_links[rid,earlier,role]:
                            # Check exact exported field hashes, not approximate dot scores.
                            left=[p.hashes[src] if len(p.hashes)>src else 0 for p in mem.ports]
                            right=[p.hashes[dst] if len(p.hashes)>dst else 0 for p in mem.ports]
                            x=torch.tensor([v-(1<<64) if v>=(1<<63) else v for v in left])
                            y=torch.tensor([v-(1<<64) if v>=(1<<63) else v for v in right])
                            different|=x[batch[row,j]]!=y[ports[col]]
                    disagree[k]+=int(different.sum())
                    if k+1<len(order) and len(row):
                        extend(k+1,torch.cat((batch[row],ports[col,None]),dim=1))
            extend(1,first[:,None])
            report.append(dict(rule=rid,owner=a,arity=len(atoms),prefixes=widths,
                               new_role_conflicting_with_prior=disagree))
    report.sort(key=lambda x:-x['prefixes'][-1])
    return dict(run=run,teacher_commits=len(s.targets),issued=zero+sum(x['prefixes'][-1] for x in report),
                zero_parent=zero,branches=report)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('folder',type=Path);p.add_argument('weights',type=Path);p.add_argument('out',type=Path)
    p.add_argument('--run',type=int,required=True);p.add_argument('--seed',type=int,default=1703)
    a=p.parse_args();torch.set_num_threads(1)
    model=load_actor(a.weights,True);report=profile(model,a.folder,a.run,a.seed)
    report['weights_sha256']=digest(a.weights)
    a.out.write_text(json.dumps(report,indent=2)+'\n')
