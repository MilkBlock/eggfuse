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


def targets(cat,snapshot,labels=None,owners=None):
    index={p.address:i for i,p in enumerate(snapshot.ports)}
    roots=defaultdict(set)
    children=defaultdict(set)
    grouped=defaultdict(lambda:defaultdict(set))
    def add(table,key,j,owner):
        table[key].add(j)
        if owners is not None:
            grouped[key][owner].add(j)
    actions=snapshot.targets if labels is None else labels
    if owners is not None and len(actions)!=len(owners):
        raise ValueError('missing certificate identity')
    for i,(rid,refs) in enumerate(actions):
        owner=owners[i] if owners is not None else None
        if not refs:
            add(roots,(rid,None),0,owner)
            continue
        js=tuple(index[a] for a in refs)
        anchor=next(i for i,j in enumerate(js) if not cat.seminaive[rid] or
                    snapshot.ports[j].version>=snapshot.rules[rid])
        order=[anchor]+[j for j in range(len(js)) if j!=anchor]
        add(roots,(rid,anchor),js[anchor],owner)
        for depth in range(1,len(js)):
            prefix=tuple(js[i] for i in order[:depth])
            add(children,(rid,anchor,prefix),js[order[depth]],owner)
    return (roots,children,grouped) if owners is not None else (roots,children)


def training_selection(root,seed):
    records=json.loads((root/'manifest.json').read_bytes())
    rows=[r for r in records if r['split']=='train']
    rng=random.Random(seed)
    rows=[r for r in rows if r['origin']=='eggcc']+rng.sample([r for r in rows if r['origin']=='random'],48)
    for r in rows:
        busy=set(r['busy_runs'])
        empty=set(range(1,r['runs']+1))-busy
        runs=set(rng.sample(sorted(busy),min(60,len(busy)))+rng.sample(sorted(empty),min(12,len(empty))))
        if r['origin']=='eggcc':
            tape=json.loads((root/r['directory']/'tape.json').read_bytes())
            runs.update(p['run'] for p in tape['requests'] if not p['parents'])
        yield r,runs


def dataset(root,seed,alternate=None,credits=None,grouped=False):
    items=[]
    vocabulary=set()
    for r,runs in training_selection(root,seed):
        folder=root/r['directory']
        observed=stream(folder,seed+r['seed'],runs,SemanticCatalog)
        other=None
        if alternate is not None:
            source=alternate['programs'][r['directory']]
            for file,key in [('tape','teacher'),('program','program'),('memory','memory')]:
                path=folder/('memory.jsonl' if file=='memory' else file+'.json')
                if hashlib.sha256(path.read_bytes()).hexdigest()!=source[key+'_sha256']:
                    raise ValueError('alternate certificates belong to another capture')
            if grouped:
                owners=defaultdict(list)
                extra_owners=defaultdict(list)
                for req in json.loads((folder/'tape.json').read_bytes())['requests']:
                    owners[req['run']].append(req['token'])
                for req in source['proofs']:
                    extra_owners[req['run']].append(req['winner'])
            other=iter(stream(folder,seed+r['seed'],runs,SemanticCatalog,source['proofs']))
        for cat,s in observed:
            if other is not None:
                _,alt=next(other)
                if s.run!=alt.run or [p.address for p in s.ports]!=[p.address for p in alt.ports]:
                    raise ValueError('alternate supervision address domain changed')
                credit_ids=(owners[s.run]+extra_owners[s.run]) if grouped else None
                credits[len(items)]=targets(cat,s,[*s.targets,*alt.targets],credit_ids)
            vocabulary.update(v for row in cat.factors for v in row)
            items.append((cat,s,*targets(cat,s),r['origin']))
    return items,sorted(vocabulary)


def objective(scores,ids,positive,groups=None):
    wanted=ints(scores,sorted(positive))
    y=torch.isin(ids,wanted)
    n=len(wanted)
    gain=max(1.,min(8.,(len(y)-n)/max(1,n)))
    if not groups:
        loss=F.binary_cross_entropy_with_logits(scores,y.to(scores.dtype),reduction='none')
        weight=1+y.to(scores.dtype)*(gain-1)
        return (loss*weight).sum()/weight.sum()
    # Give each distinct teacher commit one positive term at its best proven
    # continuation. Use the same aggregate positive/negative mass as the BCE arm.
    choices=[sorted(ports) for ports in groups.values()]
    width=max(map(len,choices))
    padded=[row+[row[0]]*(width-len(row)) for row in choices]
    positions=torch.searchsorted(ids,ints(scores,padded))
    best=scores[positions].max(dim=1).values
    positive_loss=F.softplus(-best).mean()
    negative_loss=F.softplus(scores).masked_fill(y,0).sum()
    return (positive_loss*n*gain+negative_loss)/(n*gain+len(scores)-n)


def reads(cat,s,mem,model,roots,children,rng,credit=None,tally=None):
    credited_roots,credited_children=(roots,children) if credit is None else credit[:2]
    groups={} if credit is None or len(credit)==2 else credit[2]

    def term(level,key,scores,ids):
        sampled,expanded=(roots,credited_roots) if level<2 else (children,credited_children)
        original=sampled.get(key,())
        positive=expanded.get(key,())
        if tally is not None:
            tally['added_labels_on_reads']+=len(positive)-len(original)
            tally['changed_reads']+=int(len(positive)>len(original))
        return level,scores,ids,positive,groups.get(key)
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
        rows.append(term(int(anchor is not None),(rid,anchor),scores,ids))
    for rid,anchor,prefix in rng.sample(list(children),min(6,len(children))):
        order=[anchor]+[j for j in range(len(cat.atoms[rid])) if j!=anchor]
        depth=len(prefix)
        role=order[depth]
        ids=dom.role(cat,mem,rid,anchor,role)
        x=ints(mem.nodes,[prefix])
        scores=model.pair_scores(cat,mem,rid,order[:depth],x,role,ids)[0]
        rows.append(term(2,(rid,anchor,prefix),scores,ids))
        # A typed alternative prefix is a training example only. The lookup
        # returns all of its actual children, including legitimate alternatives.
        changed=list(prefix)
        j=rng.randrange(depth)
        alternatives=dom.role(cat,mem,rid,anchor,order[j])
        changed[j]=int(alternatives[rng.randrange(len(alternatives))])
        x=ints(mem.nodes,[changed])
        scores=model.pair_scores(cat,mem,rid,order[:depth],x,role,ids)[0]
        rows.append(term(2,(rid,anchor,tuple(changed)),scores,ids))
    return rows


def train(root,out,steps,seed,modes,label_file=None,grouped=False):
    torch.set_num_threads(1)
    credits={}
    alternate=json.loads(label_file.read_bytes()) if label_file else None
    if alternate and alternate["seed"]!=seed: raise ValueError("different capture seed")
    if grouped and not alternate: raise ValueError("group credit requires verified alternatives")
    data,vocab=dataset(root,seed,alternate,credits,grouped)
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
            terms=reads(cat,s,mem,actor,roots,children,rng,credits.get(idx),counts)
            if not terms: continue
            losses=[objective(scores,ids,positive,groups) for _,scores,ids,positive,groups in terms]
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
                for level,score,ids,pos,_ in reads(cat,s,mem,actor,roots,children,rng):
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
            grouped_commit_credit=grouped,alternate_labels_sha256=hashlib.sha256(label_file.read_bytes()).hexdigest() if label_file else None,
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
    p.add_argument('--labels',type=Path)
    p.add_argument('--grouped-commit-credit',action='store_true')
    a=p.parse_args()
    train(a.root,a.out,a.steps,a.seed,a.modes,a.labels,a.grouped_commit_credit)
