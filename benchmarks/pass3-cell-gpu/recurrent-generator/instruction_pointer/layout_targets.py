"""Collect set-valued layout supervision from sealed executions of the training programs."""
import argparse
from collections import Counter,defaultdict
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import torch

from alternate_proofs import digest
from anchor_set_audit import load_actor
from higher_cell import read
from layout_credit import CreditIssuer
from online import INTERNAL,execute
from prefix_policy import Policy
from ripsat_layout import capture
from ripsat_policy import root_context
from side_boundary import address
from train_layout_bandit import LearnedChoice


@torch.no_grad()
def collect(root,name,donor,binary,weights,base,study,old,out):
    baked=study/'expanded'
    training=read(baked/'study.json')['training_traces']
    if name not in training:
        raise ValueError('only training programs may supply labels')
    trace=study/name
    meta=training[name]
    for filename,key in [('tape.json','tape'),('memory.jsonl','memory'),('program.json','program')]:
        if digest(trace/filename)!=meta[key]:
            raise ValueError('residual trace changed')
    if digest(root/name/'program.json')!=meta['program']:
        raise ValueError('source program changed')
    program=read(trace/'program.json')
    actor=load_actor(weights,True)
    seed=1703+next((r['seed'] for r in read(root/'manifest.json') if r['directory']==name),0)
    old_policy=LearnedChoice(old,base)
    if old_policy.checkpoint!=meta['policy'] or digest(weights)!=read(baked/'study.json')['root_weights']:
        raise ValueError('logging policy changed')
    def issuer(folder,policy):
        return CreditIssuer(actor,donor,program,folder,omit=True,explore=False,
                            seed=seed,policy=policy,attach=True)
    live=issuer(base,old_policy)
    probe=issuer(baked,None)
    lu={l:u for u,l in enumerate(probe.layouts) if u not in probe.withheld}
    refs,_,roots,_=capture(trace,donor,max(map(len,lu)),each_parent_first=True)
    targets={}
    for j,layouts in roots.items():
        req=refs[j]
        if req['token']>=INTERNAL:
            continue
        positive={}
        for layout,instances in layouts.items():
            u=lu.get(layout)
            if u is None:
                continue
            for boundary,ready,first,tokens in instances:
                if ready and first:
                    # Residual children are opportunities. Internal children are
                    # included so the policy also learns to retain existing work.
                    gain=sum(t>=INTERNAL for t in tokens[1:])
                    if gain:
                        alternatives=positive.setdefault(u,{})
                        alternatives[boundary]=max(gain,alternatives.get(boundary,0))
        if positive:
            targets[req['token']]=positive
    rows=[]
    menus={}
    receipts=[]
    stats=Counter()
    def snapshot(catalog,history,snap):
        nonlocal state
        domains=defaultdict(list)
        for p in snap.ports:
            domains[p.table].append(p)
        state=history,snap,domains,{}
    def packets(requests):
        history,snap,domains,eligible=state
        for req in requests:
            rid=req['rule']
            if rid not in eligible:
                eligible[rid]=tuple(u for u in probe.choices[rid] if u not in probe.withheld and
                    all(probe.rule[probe.layouts[u][i][0]] in snap.rules for i in probe.groups[u][0]))
            options=eligible[rid]
            positives=targets.get(req['token'],{})
            if not positives.keys()<=set(options):
                raise ValueError('observed layout missing from legal action menu')
            if not options:
                continue
            menu=menus.setdefault(options,len(menus))
            targets_for_root=[]
            for u,alternatives in positives.items():
                result=probe.bind_layout(req,u,history,domains)
                predicted=tuple((*address(p),p['version']) for p in result.boundary) if result else None
                targets_for_root.append((u,max(alternatives.values()),alternatives.get(predicted,0)))
            fields=[tuple(history.visible[address(p)]['hashes']) for p in req['parents']]
            x=root_context(fields,actor.width)
            rows.append((menu,x.tolist(),targets_for_root))
            stats['root_decisions']+=1
            stats['with_observed_gain']+=bool(positives)
            stats['with_reproduced_boundary_gain']+=any(reached for _,_,reached in targets_for_root)
    state=None
    with TemporaryDirectory() as tmp:
        path=Path(tmp)/'layouts.json'
        path.write_text(json.dumps(live.receiver_layouts(),separators=(',',':')))
        run=execute(binary,root/name/'program.json',actor,seed,assist=True,prefix_policy=Policy(32),
                    graph_issuer=live,layout_file=path,observe_packets=packets,observe_snapshot=snapshot,
                    frame_observer=lambda frame:receipts.extend(frame['accepted']))
    if receipts!=refs or run['state_sha']!=read(trace/'opportunity.json')['native']['state_sha']:
        raise ValueError('collected decisions differ from the archived run')
    out.mkdir(parents=True,exist_ok=True)
    dst=out/(name+'.json.gz')
    with gzip.open(dst,'wt') as f:
        json.dump(dict(menus=list(menus),rows=rows),f,separators=(',',':'))
    (out/(name+'.json')).write_text(json.dumps(dict(program=name,catalog=digest(baked/'catalog.json'),
        trace=meta,binary=digest(binary),data=digest(dst),stats=stats),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('root','donor','binary','weights','base','experiment','old','out'):
        p.add_argument(key,type=Path)
    p.add_argument('--cases',nargs='+',required=True)
    a=p.parse_args()
    torch.set_num_threads(1)
    for name in a.cases:
        collect(a.root,name,read(a.donor/'program.json'),a.binary,a.weights,a.base,a.experiment,a.old,a.out)
