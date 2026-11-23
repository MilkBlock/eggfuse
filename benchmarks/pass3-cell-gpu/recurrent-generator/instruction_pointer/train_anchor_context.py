"""Fit the multi-parent anchor decision with the rest of the token policy frozen."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random

import torch

from anchor_context import ContextActor
from anchor_set import Domains
from train_anchor_set import dataset, objective


def fit(root,labels,initial,out,steps,seed):
    torch.set_num_threads(1)
    checkpoint=torch.load(initial,weights_only=True,map_location='cpu')
    proofs=json.loads(labels.read_bytes())
    if proofs['seed']!=seed: raise ValueError('certificate capture seed differs')
    credits={}
    data,_=dataset(root,seed,proofs,credits,True)
    indices=list(range(len(data)))
    rng=random.Random(seed)
    rng.shuffle(indices)
    zero={i for i in indices if any(a is None for _,a in data[i][2])}
    # Reuse the split from anchor-set training. Zero-parent rules have no siblings to read.
    train=[i for i in indices if i not in zero][max(1,len(indices)//6):]
    by_origin={k:[i for i in train if data[i][-1]==k] for k in ('random','eggcc')}
    for mode in ('blind','context'):
        torch.manual_seed(seed)
        model=ContextActor(checkpoint['vocabulary'],checkpoint['names'],blind=mode=='blind')
        delta=model.load_state_dict(checkpoint['parameters'],strict=False)
        if set(delta.missing_keys)!={n for n,_ in model.named_parameters() if n.startswith('context_')} or delta.unexpected_keys:
            raise ValueError('unexpected frozen checkpoint')
        for n,p in model.named_parameters():
            p.requires_grad_(n.startswith('context_'))
        model.to('mps')
        opt=torch.optim.AdamW((p for p in model.parameters() if p.requires_grad),lr=.003)
        rng=random.Random(seed)
        counts=Counter()
        for step in range(steps):
            i=rng.choice(by_origin['eggcc' if step%3!=0 else 'random'])
            cat,s,_,_,_=data[i]
            roots,_,groups=credits[i]
            with torch.no_grad():
                mem=model.memory(cat,s)
                dom=Domains(mem)
            positive=[]
            negative=[]
            for rid in s.rules:
                atoms=cat.atoms[rid]
                if len(atoms)<2: continue
                for a in range(len(atoms) if cat.seminaive[rid] else 1):
                    if len(dom.role(cat,mem,rid,a,a)):
                        (positive if (rid,a) in roots else negative).append((rid,a))
            selected=rng.sample(positive,min(5,len(positive)))+rng.sample(negative,min(5,len(negative)))
            if not selected: continue
            losses=[]
            for rid,role in selected:
                ids=dom.role(cat,mem,rid,role,role)
                scores=model.root_scores(cat,mem,rid,role,ids,dom)-model.thresholds[1]
                key=(rid,role)
                losses.append(objective(scores,ids,roots.get(key,()),groups.get(key)))
                counts['scored_anchors']+=len(ids)
                counts['positive_ports']+=len(roots.get(key,()))
            opt.zero_grad(set_to_none=True)
            loss=torch.stack(losses).mean()
            if not loss.isfinite():raise ValueError('nonfinite root loss')
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(),3.)
            opt.step()
            counts['updates']+=1
        state=model.cpu().state_dict()
        if any(not torch.equal(state[k],v) for k,v in checkpoint['parameters'].items()):
            raise ValueError('parent decoder or threshold changed')
        path=out/mode
        path.mkdir(exist_ok=True,parents=True)
        weights=path/'model.pt'
        torch.save(dict(format='anchor-context-v1',blind=model.blind,vocabulary=checkpoint['vocabulary'],
                        names=checkpoint['names'],parameters=state),weights)
        (path/'training.json').write_text(json.dumps(dict(mode=mode,device='mps',seed=seed,steps=steps,
            counts=counts,weights_sha256=hashlib.sha256(weights.read_bytes()).hexdigest(),
            frozen_sha256=hashlib.sha256(initial.read_bytes()).hexdigest(),
            labels_sha256=hashlib.sha256(labels.read_bytes()).hexdigest()),indent=2)+'\n')
        print(mode,dict(counts),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('root','labels','initial','out'):p.add_argument(name,type=Path)
    p.add_argument('--steps',type=int,default=384)
    p.add_argument('--seed',type=int,default=1703)
    a=p.parse_args()
    fit(a.root,a.labels,a.initial,a.out,a.steps,a.seed)
