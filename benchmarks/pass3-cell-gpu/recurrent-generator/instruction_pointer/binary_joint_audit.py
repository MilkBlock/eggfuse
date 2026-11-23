"""On binary rules, isolate the effect of pruning an anchor before scoring complete pairs."""
import argparse
import json
import math
from collections import Counter
from pathlib import Path

import torch
from torch.nn import functional as F

from alternate_proofs import digest
from anchor_set import Domains
from anchor_set_audit import check,load_actor
from higher_cell import read
from history import History
from prefix_policy import Policy
from prefix_recovery import Recovery,bounded_indices,select


def top_pool(previous, scores, rows, cols, budget):
    # Keep one extra score so ties at the final boundary can be discarded.
    values,linear=scores.flatten().topk(min(budget+1,scores.numel()))
    indices=torch.stack((rows[linear//len(cols)],cols[linear%len(cols)]),1)
    if previous is not None:
        pv,pi=previous
        values=torch.cat((pv,values))
        indices=torch.cat((pi,indices))
        values,which=values.topk(min(budget+1,len(values)))
        indices=indices[which]
    return values,indices


def equally_many(a,b,k):
    if a is None or b is None:
        return [],[]
    cap=min(k,len(a[0]),len(b[0]))
    while cap:
        left,right=(bounded_indices(p[0],cap) for p in (a,b))
        if len(left)==len(right):
            return a[1][left].tolist(),b[1][right].tolist()
        cap=min(len(left),len(right))
    return [],[]


@torch.no_grad()
def measure(folder,memory,weights,head,binary):
    program=read(folder/'program.json')
    tape=read(folder/'tape.json')
    actor=load_actor(weights,True)
    cat=actor.catalog_type(program)
    history=History(cat,3434)
    nodes=actor.template_graph(cat)
    policy=Policy(32,recovery=Recovery(head,weights))
    binary_rules={r for r,atoms in cat.atoms.items() if len(atoms)==2}
    counters=Counter()
    requests=[]
    membership=[]
    with memory.open() as stream:
        for line in stream:
            snap=history.snapshot(json.loads(line))
            mem=actor.memory(cat,snap,nodes)
            dom=Domains(mem)
            for rid in snap.rules.keys() & binary_rules:
                for anchor in range(2 if cat.seminaive[rid] else 1):
                    role=1-anchor
                    rows=dom.role(cat,mem,rid,anchor,anchor)
                    cols=dom.role(cat,mem,rid,anchor,role)
                    if not len(rows) or not len(cols): continue
                    keep=select(actor,cat,mem,dom,rid,anchor,(anchor,role),0,dom.empty.reshape(1,0),policy,Counter()).flatten()
                    counters['legal_pairs']+=len(rows)*len(cols)
                    counters['pairs_after_prefix']+=len(keep)*len(cols)
                    first=actor.root_scores(cat,mem,rid,anchor,rows,dom)-actor.thresholds[1]
                    full=pruned=None
                    for ids in torch.arange(len(rows)).split(max(1,65536//len(cols))):
                        js=rows[ids]
                        last=actor.pair_scores(cat,mem,rid,(anchor,),js[:,None],role,cols)-actor.thresholds[2]
                        scores=F.logsigmoid(first[ids,None])+F.logsigmoid(last)
                        full=top_pool(full,scores,js,cols,32)
                        allowed=torch.isin(js,keep)
                        if allowed.any():
                            pruned=top_pool(pruned,scores[allowed],js[allowed],cols,32)
                    small,wide=equally_many(pruned,full,32)
                    all_pairs=full[1][bounded_indices(full[0],32)].tolist()
                    # Each proposal is checked once. Arm membership is offline accounting.
                    arms=[set(map(tuple,rows_)) for rows_ in (small,wide,all_pairs)]
                    counters['groups']+=1
                    counters['no_matched_slots']+=int(not small)
                    for x in sorted(set.union(*arms)):
                        parents=[]
                        for j in (x if anchor==0 else x[::-1]):
                            port=mem.ports[j]
                            alias,pc=port.address
                            parents.append(dict(address=dict(token=history.inverse[alias],op=pc),version=port.version))
                        requests.append(dict(token=len(requests)+1,run=snap.run,rule=rid,parents=parents))
                        membership.append([x in items for items in arms])
    verdicts=check(folder,binary,tape,requests)['recall_verdicts']
    reached=[set() for _ in range(3)]
    stats=[Counter() for _ in range(3)]
    required={p['token'] for p in tape['requests'] if p['rule'] in binary_rules}
    for run,token,winner,reason in verdicts:
        if run!=requests[token-1]['run'] or winner is not None and winner not in required:
            raise ValueError('wrong reference commit or Run')
        for arm,issued in enumerate(membership[token-1]):
            if issued:
                stats[arm]['paid']+=1
                if winner is None: stats[arm][reason]+=1
                else:
                    stats[arm]['valid_proofs']+=1
                    reached[arm].add(winner)
    if stats[0]['paid']!=stats[1]['paid']: raise ValueError('unequal paid budget')
    result={}
    for name,hits,counts in zip(('retained_anchors','all_anchors_matched','all_anchors_full'),reached,stats,strict=True):
        result[name]=dict(distinct=len(hits),duplicates=counts['valid_proofs']-len(hits),counts=counts)
    return dict(mode='binary root shadow on sealed teacher Runs',binary=digest(binary),actor=digest(weights),
                recovery=policy.recovery.checkpoint,tape=digest(folder/'tape.json'),memory=digest(memory),
                seed=3434,source_runs=history.run,required=len(required),all_commits=len(tape['requests']),
                work=counters,arms=result,only_retained=len(reached[0]-reached[1]),only_joint=len(reached[1]-reached[0]))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('folder','memory','weights','head','binary','out'):p.add_argument(k,type=Path)
    a=p.parse_args()
    torch.set_num_threads(1)
    a.out.write_text(json.dumps(measure(a.folder,a.memory,a.weights,a.head,a.binary),indent=2)+'\n')
