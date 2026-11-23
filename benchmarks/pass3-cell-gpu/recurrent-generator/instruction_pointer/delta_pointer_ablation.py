"""Locate the first lost recorded proof, after verifying every alternate emitted binding."""
import argparse
import csv
import json
from collections import Counter,defaultdict
from pathlib import Path

import torch

from alternate_proofs import digest
from anchor_set import Domains
from anchor_set_audit import check,load_actor
from higher_cell import read
from history import History,address
from prefix_policy import Policy,select_frontier
from prefix_recovery import Recovery


@torch.no_grad()
def measure(folder,weights,head,binary,output,mode,historical=False):
    prog=read(folder/'program.json')
    tape=read(folder/'tape.json')
    actor=load_actor(weights,True)
    cat=actor.catalog_type(prog)
    history=History(cat,3434,cache_ports=True)
    nodes=actor.template_graph(cat)
    policy=Policy(32,recovery=None if historical else Recovery(head,weights),read_order='source' if mode=='source' or mode=='oracle-source' else 'delta')
    targets=defaultdict(list)
    for req in tape['requests']: targets[req['run']].append(req)
    losses={}; proposals=[]; changed=0; work=Counter()
    with (folder/'memory.jsonl').open() as stream:
        for line in stream:
            snap=history.snapshot(json.loads(line))
            mem=actor.memory(cat,snap,nodes)
            dom=Domains(mem); idx={p.address:i for i,p in enumerate(mem.ports)}
            paths=defaultdict(list)
            for req in targets[snap.run]:
                rid=req['rule']; token=req['token']
                if rid not in snap.rules:
                    losses[token]=('unscheduled',0,'');continue
                js=[]
                for p in req['parents']:
                    j=idx.get(history.rename(address(p['address'])))
                    if j is None or mem.ports[j].version!=p['version']:
                        losses[token]=('invisible',len(js)+1,'');break
                    js.append(j)
                if token in losses: continue
                anchor=next((i for i,j in enumerate(js) if not cat.seminaive[rid] or mem.ports[j].version>=snap.rules[rid]),0)
                order=cat.read_order(rid,anchor,policy.read_order) if js else ()
                paths[rid,anchor].append((token,tuple(js[i] for i in order)))
            def emit(rid,order,row):
                parents=[None]*len(order)
                for role,j in zip(order,row,strict=True):
                    p=mem.ports[j];alias,pc=p.address
                    parents[role]=dict(address=dict(token=history.inverse[alias],op=pc),version=p.version)
                proposals.append(dict(run=snap.run,token=len(proposals)+1,rule=rid,parents=parents))
            for rid,wm in snap.rules.items():
                n=len(cat.atoms[rid]);activated=False
                if not n:
                    selected=(not cat.seminaive[rid] or wm==0) and actor.root_scores(cat,mem,rid,None,None,dom).item()>=actor.thresholds[0]
                    if selected:emit(rid,(),())
                    else:
                        for token,_ in paths[rid,0]:losses[token]=('rule',0,'zero-parent score')
                    continue
                for anchor in range(n if cat.seminaive[rid] else 1):
                    order=cat.read_order(rid,anchor,policy.read_order)
                    changed+=int(order!=cat.read_order(rid,anchor,'source'))
                    tracked=paths[rid,anchor]
                    frontier=dom.empty.reshape(1,0)
                    for depth,role in enumerate(order):
                        if mode.startswith('oracle') and depth==0:
                            ids=sorted({js[0] for _,js in tracked})
                            frontier=dom.empty.new_tensor(ids).reshape(-1,1)
                            if len(ids) and not torch.isin(frontier.flatten(),dom.role(cat,mem,rid,anchor,role)).all():
                                raise ValueError('teacher anchor outside delta domain')
                        else:
                            frontier=select_frontier(actor,cat,mem,dom,rid,anchor,order,depth,frontier,policy,None,work,False)
                        if depth==0 and len(frontier):activated=True
                        if tracked:
                            reached=set(map(tuple,frontier.tolist()))
                            remaining=[]
                            for token,js in tracked:
                                if js[:depth+1] in reached:
                                    remaining.append((token,js));continue
                                ids=dom.role(cat,mem,rid,anchor,role)
                                loc=(ids==js[depth]).nonzero().flatten()
                                if not len(loc):
                                    losses[token]=('invisible',depth+1,'outside seminaive role')
                                    continue
                                prior=dom.empty.new_tensor([js[:depth]]).reshape(1,depth)
                                scores=(actor.pair_scores(cat,mem,rid,order[:depth],prior,role,ids) if depth else
                                        actor.root_scores(cat,mem,rid,role,ids,dom)[None])
                                margin=scores-actor.thresholds[2 if depth else 1]
                                qualifies=margin[0,loc].item()>=0 or (policy.recovery is not None and policy.recovery.scores(
                                    cat,mem,rid,order,depth,prior,ids,margin)[0,loc].item()>=policy.recovery.cut)
                                losses[token]=('anchor' if not depth else 'parent',depth+1,'cap/quota/tie' if qualifies else 'threshold')
                            tracked=remaining
                        if not len(frontier):break
                    for row in frontier.tolist():emit(rid,order,row)
                if not activated:
                    for a in range(n):
                        for token,_ in paths[rid,a]:
                            if token in losses and losses[token][0]=='anchor':
                                losses[token]=('rule',1,losses[token][2])
    verdict=check(folder,binary,tape,proposals)
    hits={winner for _,_,winner,_ in verdict['recall_verdicts'] if winner is not None}
    rejects=Counter(reason for _,_,w,reason in verdict['recall_verdicts'] if w is None)
    by_signature={(req['run'],req['rule'],tuple((address(p['address']),p['version']) for p in req['parents'])):req['token']
                  for req in tape['requests']}
    for run,t,w,reason in verdict['recall_verdicts']:
        if w is None:
            q=proposals[t-1]
            ident=by_signature.get((run,q['rule'],tuple((address(p['address']),p['version']) for p in q['parents'])))
            if ident is not None:losses[ident]=('verifier',len(q['parents']),reason)
    missing=Counter()
    with output.with_suffix('.csv').open('w') as stream:
        writer=csv.writer(stream);writer.writerow(('run','rule','teacher_commit','loss','first_depth','cause'))
        for req in tape['requests']:
            token=req['token']
            if token in hits:continue
            reason=losses[token]
            writer.writerow((req['run'],req['rule'],token,*reason))
            missing['/'.join(map(str,reason))]+=1
    if len(hits)+sum(missing.values())!=len(tape['requests']):raise ValueError('unattributed submission')
    table_hits=sum(req['token'] in hits and bool(req['parents']) for req in tape['requests'])
    valid=sum(w is not None for _,_,w,_ in verdict['recall_verdicts'])
    output.write_text(json.dumps(dict(mode=mode,actor=digest(weights),recovery=policy.recovery.checkpoint if policy.recovery else None,binary=digest(binary),
        tape=digest(folder/'tape.json'),runs=history.run,required=len(tape['requests']),distinct=len(hits),table_hits=table_hits,
        paid=len(proposals),duplicates=valid-len(hits),rejected=rejects,loss=missing,changed_routes=changed,work=work),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('folder','weights','head','binary','output'):p.add_argument(k,type=Path)
    p.add_argument('--mode',required=True,choices=['source','delta','oracle','oracle-source'])
    p.add_argument('--historical',action='store_true')
    a=p.parse_args()
    torch.set_num_threads(1)
    measure(a.folder,a.weights,a.head,a.binary,a.output,a.mode,a.historical)
