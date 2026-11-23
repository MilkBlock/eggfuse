"""Fit one-wave set issuance on complete teacher binding sets, under matched symbol treatments."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import random

import torch
from torch.nn import functional as F

from actor import ints
from anchor_set import AnchorSetActor, Domains
from history import stream
from semantic_catalog import SemanticCatalog


def targets(cat,snapshot,labels=None):
    index={p.address:i for i,p in enumerate(snapshot.ports)}
    roots=defaultdict(set)
    children=defaultdict(set)
    for rid,refs in snapshot.targets if labels is None else labels:
        if not refs:
            roots[rid,None].add(0)
            continue
        js=tuple(index[a] for a in refs)
        anchor=next(i for i,j in enumerate(js) if not cat.seminaive[rid] or
                    snapshot.ports[j].version>=snapshot.rules[rid])
        order=[anchor]+[j for j in range(len(js)) if j!=anchor]
        roots[rid,anchor].add(js[anchor])
        for depth in range(1,len(js)):
            prefix=tuple(js[i] for i in order[:depth])
            children[rid,anchor,prefix].add(js[order[depth]])
    return roots,children


def dataset(root,seed):
    records=json.loads((root/'manifest.json').read_bytes())
    rows=[r for r in records if r['split']=='train']
    rng=random.Random(seed)
    rows=[r for r in rows if r['origin']=='eggcc']+rng.sample([r for r in rows if r['origin']=='random'],48)
    items=[]
    vocabulary=set()
    for r in rows:
        busy=set(r['busy_runs'])
        empty=set(range(1,r['runs']+1))-busy
        runs=set(rng.sample(sorted(busy),min(60,len(busy)))+rng.sample(sorted(empty),min(12,len(empty))))
        if r['origin']=='eggcc':
            tape=json.loads((root/r['directory']/'tape.json').read_bytes())
            runs.update(p['run'] for p in tape['requests'] if not p['parents'])
        for cat,s in stream(root/r['directory'],seed+r['seed'],runs,SemanticCatalog):
            vocabulary.update(v for row in cat.factors for v in row)
            items.append((cat,s,*targets(cat,s),r['origin']))
    return items,sorted(vocabulary)


def objective(scores,ids,positive):
    wanted=ints(scores,sorted(positive))
    # Build the full target vector for this read before any loss balancing.
    y=torch.isin(ids,wanted).to(scores.dtype)
    loss=F.binary_cross_entropy_with_logits(scores,y,reduction='none')
    gain=max(1.,min(8.,(len(y)-len(positive))/max(1,len(positive))))
    weight=1+y*(gain-1)
    return (loss*weight).sum()/weight.sum()


def reads(cat,s,mem,model,roots,children,rng):
    dom=Domains(mem)
    legal=[]
    for rid,wm in mem.rules.items():
        atoms=cat.atoms[rid]
        if not atoms:
            if not cat.seminaive[rid] or wm==0:
                legal.append((rid,None))
        else:
            legal.extend((rid,i) for i in range(len(atoms) if cat.seminaive[rid] else 1)
                         if len(dom.role(cat,mem,rid,i,i)))
    positives=list(roots)
    negatives=[x for x in legal if x not in roots]
    rows=[]
    for rid,anchor in rng.sample(positives,min(3,len(positives)))+rng.sample(negatives,min(3,len(negatives))):
        ids=ints(mem.nodes,[0]) if anchor is None else dom.role(cat,mem,rid,anchor,anchor)
        scores=model.root_scores(cat,mem,rid,anchor,ids)
        rows.append((int(anchor is not None),scores,ids,roots.get((rid,anchor),())))
    for rid,anchor,prefix in rng.sample(list(children),min(6,len(children))):
        order=[anchor]+[j for j in range(len(cat.atoms[rid])) if j!=anchor]
        depth=len(prefix)
        role=order[depth]
        ids=dom.role(cat,mem,rid,anchor,role)
        x=ints(mem.nodes,[prefix])
        rows.append((2,model.pair_scores(cat,mem,rid,order[:depth],x,role,ids)[0],ids,children[rid,anchor,prefix]))
        # A typed alternative prefix is a training example only. The lookup
        # returns all of its actual children, including legitimate alternatives.
        changed=list(prefix)
        j=rng.randrange(depth)
        alternatives=dom.role(cat,mem,rid,anchor,order[j])
        changed[j]=int(alternatives[rng.randrange(len(alternatives))])
        x=ints(mem.nodes,[changed])
        rows.append((2,model.pair_scores(cat,mem,rid,order[:depth],x,role,ids)[0],ids,
                     children.get((rid,anchor,tuple(changed)),())))
    return rows


def train(root,out,steps,seed,modes):
    torch.set_num_threads(1)
    data,vocab=dataset(root,seed)
    # Select calibration snapshots once. Held programs and held templates stay untouched.
    rng=random.Random(seed)
    index=list(range(len(data)))
    rng.shuffle(index)
    n=max(1,len(index)//6)
    zero=[i for i in index if any(role is None for rid,role in data[i][2])]
    zero_set=set(zero)
    others=[i for i in index if i not in zero_set]
    if len(zero)<2: raise ValueError("need train and calibration zero-parent targets")
    nz=max(1,len(zero)//2)
    train_ix,cal=others[n:]+zero[nz:],others[:n]+zero[:nz]
    torch.manual_seed(seed)
    common=AnchorSetActor(vocab)
    for mode in modes:
        torch.manual_seed(seed)
        actor=AnchorSetActor(vocab,mode)
        state=actor.load_state_dict(common.state_dict(),strict=False)
        if state.unexpected_keys or set(state.missing_keys)-{'user_names.weight'}:
            raise ValueError('different shared initialization')
        actor.to('mps')
        optimizer=torch.optim.AdamW(actor.parameters(),lr=.002)
        rng=random.Random(seed)
        counts=Counter()
        groups={origin:[i for i in train_ix if data[i][-1]==origin] for origin in ('eggcc','random')}
        for step in range(steps):
            actor.rename_seed=rng.getrandbits(48)
            idx=rng.choice(groups['eggcc' if step%3!=0 else 'random'])
            if step%24==0: idx=rng.choice(zero[nz:])
            cat,s,roots,children,_=data[idx]
            mem=actor.memory(cat,s)
            terms=reads(cat,s,mem,actor,roots,children,rng)
            if not terms: continue
            losses=[objective(scores,ids,positive) for _,scores,ids,positive in terms]
            loss=torch.stack(losses).mean()
            if not loss.isfinite(): raise ValueError('nonfinite anchor loss')
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(actor.parameters(),3.)
            optimizer.step()
            counts['updates']+=1
            counts['reads']+=len(terms)
        actor.cpu().eval()
        # Common threshold-selection rule applied independently to each model.
        # Maximize F1 on calibration reads. Tied scores cross as a group.
        calibration=defaultdict(list)
        with torch.no_grad():
            for i in cal:
                cat,s,roots,children,_=data[i]
                actor.rename_seed=rng.getrandbits(48)
                mem=actor.memory(cat,s)
                for level,score,ids,pos in reads(cat,s,mem,actor,roots,children,rng):
                    y=torch.isin(ids,ints(ids,sorted(pos))).long()
                    calibration[level].append((score,y))
            report={}
            for level in range(3):
                if level not in calibration: raise ValueError('missing calibration level')
                scores,labels=map(torch.cat,zip(*calibration[level]))
                values,order=scores.sort(descending=True)
                tp=labels[order].cumsum(0)
                cut=torch.cat((values[1:]!=values[:-1],torch.tensor([True])))
                f1=(2*tp/(torch.arange(1,len(tp)+1)+int(labels.sum())).clamp_min(1)).masked_fill(~cut,-1)
                best=int(f1.argmax())
                if not int(tp[best]): raise ValueError('no positive calibration coverage')
                actor.thresholds[level]=values[best]
                report[level]=dict(threshold=float(values[best]),positives=int(labels.sum()),
                                   decisions=len(scores),f1=float(f1[best]))
        folder=out/mode
        folder.mkdir(parents=True,exist_ok=True)
        path=folder/'model.pt'
        torch.save(dict(format='parallel-anchor-v1',names=mode,vocabulary=vocab,parameters=actor.state_dict()),path)
        (folder/'training.json').write_text(json.dumps(dict(mode=mode,device='mps',seed=seed,steps=steps,
            training_runs=len(train_ix),calibration_runs=len(cal),semantic_categories=len(vocab),counts=counts,
            parameters=sum(p.numel() for p in actor.parameters()),calibration=report,
            weights_sha256=hashlib.sha256(path.read_bytes()).hexdigest()),indent=2)+'\n')
        print(mode,dict(counts),report,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('root',type=Path)
    p.add_argument('out',type=Path)
    p.add_argument('--steps',type=int,default=384)
    p.add_argument('--seed',type=int,default=1703)
    p.add_argument('--modes',nargs='+',default=['structural','named','renamed'],choices=['structural','named','renamed'])
    a=p.parse_args()
    train(a.root,a.out,a.steps,a.seed,a.modes)
