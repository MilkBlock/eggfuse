"""Train and test one higher-Cell scorer over teacher executions and a frozen Bake library."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import random

import torch
from torch.nn import functional as F

from anchor_set_audit import load_actor
from alternate_proofs import digest
from higher_cell import read
from ripsat_layout import capture, iterative_layouts
from ripsat_policy import GraphBank, root_context, CellScorer
from side_boundary import address


def layout_id(layout):
    return hashlib.sha256(json.dumps(layout,separators=(',',':')).encode()).hexdigest()


def materialize(folder, data, indices, choices, width):
    refs,mapped,by_root,_=data
    index=defaultdict(list)
    for j,r in enumerate(refs):
        rid=mapped[r['rule']]
        if rid in choices:
            index[r['run']].append((j,r,rid))
    result=[]
    visible={}
    with (folder/'memory.jsonl').open() as stream:
        for line in stream:
            frame=json.loads(line)
            for a in frame['retired']:
                del visible[a['token'],a['op']]
            for a,row in frame['updates']:
                visible[a['token'],a['op']]=row
            for j,req,rid in index[frame['run']]:
                positive={}
                for layout,instances in by_root.get(j,{}).items():
                    uid=indices.get(layout)
                    if uid is not None:
                        # Jointly ready boundary plus first eligible schedule of each later step.
                        positive[uid]=any(ready and first for _,ready,first,_ in instances)
                fields=[visible[address(ref)]['hashes'] for ref in req['parents']]
                result.append((rid,root_context(fields,width),positive))
    return result


@torch.no_grad()
def evaluate(model,codes,rows,choices,layouts,held):
    counts=defaultdict(Counter)
    for group,subset in [('all',set(range(len(layouts)))),('held_layout',held)]:
        compatible={r:[i for i in opts if i in subset] for r,opts in choices.items()}
        for rid,context,observed in rows:
            options=compatible[rid]
            if not options:
                continue
            scores=model(context.expand(len(options),-1),codes[options])
            for k,label in enumerate(('observed','ready')):
                stats=counts[group+'_'+label]
                positives=[u for u in observed if u in subset and (not k or observed[u])]
                stats['decisions']+=1
                if positives:
                    stats['roots_with_observed_target']+=1
                i=int(scores[:,k].argmax())
                if scores[i,k]>0:
                    winner=options[i]
                    stats['issued']+=1
                    if winner in positives:
                        stats['selected_recorded_target']+=1
                        stats['steps_in_selected_targets']+=len(layouts[winner])
    return counts


def run(root,donor_folder,weights,out,limit,size,updates,extra=(),grow_consumers=False):
    manifest=read(root/'manifest.json')
    training=[root/r['directory'] for r in manifest if r['origin']=='eggcc' and r['split']=='train']
    if donor_folder.resolve() not in [f.resolve() for f in training]:
        raise ValueError('donor must be a training program')
    donor=read(donor_folder/'program.json')
    archived={f.name:capture(f,donor,limit,grow_consumers=grow_consumers) for f in training}
    support=Counter()
    ready_support=Counter()
    for _,_,roots,_ in archived.values():
        for cases in roots.values():
            support.update(cases.keys())
            ready_support.update(l for l,occ in cases.items() if any(ready and first for _,ready,first,_ in occ))
    original=iterative_layouts(donor,donor['iterative_bake'])
    selected=set(original)
    for layout in sorted(support,key=lambda l:(-ready_support[l]*(len(l)-1),-support[l],l)):
        if size is not None and len(selected)>=size:
            break
        selected.add(layout)
    layouts=sorted(selected)
    choices=defaultdict(list)
    for i,layout in enumerate(layouts):
        choices[layout[0][0]].append(i)
    held={i for i,l in enumerate(layouts) if int(layout_id(l)[:8],16)%8==0}
    train_ids=set(range(len(layouts)))-held
    actor=load_actor(weights,True)
    cat=actor.catalog_type(donor)
    with torch.no_grad():
        nodes=actor.template_graph(cat).cpu()
    graphs=GraphBank(layouts,cat,nodes)
    idx={l:i for i,l in enumerate(layouts)}
    rows=[row for f in training for row in materialize(f,archived[f.name],idx,choices,actor.width)]
    del archived
    rng=random.Random(1703)
    pairs=[]
    for j,(rid,_,obs) in enumerate(rows):
        positives=[u for u in obs if u in train_ids]
        unseen=[u for u in choices[rid] if u in train_ids and u not in obs]
        for u in positives+rng.sample(unseen,min(len(unseen),max(1,len(positives)))):
            pairs.append((j,u,float(u in obs),float(obs.get(u,False))))
    # Each training epoch sees every recorded positive template instance. Both heads
    # use the same weights across every layout depth and external atom count.
    device='mps'
    contexts=torch.stack([r[1] for r in rows]).to(device)
    items=torch.tensor(pairs)
    ji=items[:,0].long().to(device)
    labels=items[:,2:].to(device)
    torch.manual_seed(1703)
    model=CellScorer(actor.width).to(device)
    opt=torch.optim.AdamW(model.parameters(),lr=.003)
    order=list(range(len(pairs)))
    covered=set()
    actual=0
    epochs=0
    while actual<updates or not epochs:
        rng.shuffle(order)
        for start in range(0,len(order),256):
            batch=order[start:start+256]
            # Compact the graph batch before running shared message passing.
            compact,inverse=torch.unique(items[batch,1].long(),return_inverse=True)
            covered.update(compact.tolist())
            keys=model.encode(graphs.batch(compact,device))
            pred=model(contexts[ji[batch]],keys[inverse.to(device)])
            loss=F.binary_cross_entropy_with_logits(pred,labels[batch])
            opt.zero_grad()
            loss.backward()
            opt.step()
            actual+=1
        epochs+=1
    out.mkdir(parents=True,exist_ok=True)
    model=model.cpu().eval()
    torch.save(model.state_dict(),out/'shared.pt')
    with torch.no_grad():
        codes=graphs.encode(model)
    out.joinpath('catalog.json').write_text(json.dumps(layouts,separators=(',',':'))+'\n')
    report=dict(schema='eggfuse-higher-layout-study/v1',mode='teacher-snapshot ranking',root_weights=digest(weights),
                weights=digest(out/'shared.pt'),catalog_sha=digest(out/'catalog.json'),updates=actual,epochs=epochs,
                ready_training_layouts=len(ready_support),ready_catalog_layouts=sum(l in ready_support for l in layouts),
                grow_consumers=grow_consumers,selection="all_observed" if size is None else "bounded",
                distinct_step_vectors=len(graphs.steps)-1,distinct_edge_vectors=len(graphs.edges)-1,
                positive_by_size=dict(Counter(len(layouts[u]) for u in {u for _,u,y,_ in pairs if y})),
                ready_positive_by_size=dict(Counter(len(layouts[u]) for u in {u for _,u,_,y in pairs if y})),
                max_steps=limit,compiled=len(layouts),native_join_layouts=len(original),observed_layouts=len(support),
                train_layouts_in_gradient=len(covered),positive_gradient_layouts=len({u for _,u,y,_ in pairs if y}),
                held_layouts=len(held),depths=dict(Counter(map(len,layouts))),training_pairs=len(pairs),
                training={f.name:digest(f/'tape.json') for f in training},programs={})
    if covered & held:
        raise ValueError('held-out template contributed gradients')
    evaluation={r['directory'] for r in manifest if r['origin']=='eggcc' and r['split']!='train'} | set(extra)
    if any((root/name).resolve() in [f.resolve() for f in training] for name in evaluation):
        raise ValueError('evaluation overlaps training')
    for name in sorted(evaluation):
        f=root/name
        data=capture(f,donor,limit,grow_consumers=grow_consumers)
        rows=materialize(f,data,idx,choices,actor.width)
        report['programs'][f.name]=evaluate(model,codes,rows,choices,layouts,held)
    (out/'study.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for k in ('root','donor','weights','out'):
        parser.add_argument(k,type=Path)
    parser.add_argument('--steps',type=int,default=10)
    selection=parser.add_mutually_exclusive_group()
    selection.add_argument('--size',type=int,default=1024)
    selection.add_argument('--all-observed',action='store_true',
                           help='include every layout extracted from the training programs plus iterative joins')
    parser.add_argument('--updates',type=int,default=320)
    parser.add_argument('--grow-consumers',action='store_true',help='also grow root-ready graphs through their actual consumers')
    parser.add_argument('--extra-eval',nargs='*',default=[])
    a=parser.parse_args()
    torch.set_num_threads(1)
    run(a.root,a.donor,a.weights,a.out,a.steps,None if a.all_observed else a.size,a.updates,a.extra_eval,a.grow_consumers)
