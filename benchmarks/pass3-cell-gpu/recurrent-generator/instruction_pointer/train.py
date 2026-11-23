"""GPU set supervision for complete proposals on native random programs."""
import argparse
import hashlib
from collections import Counter
from mixed_training import batches
from itertools import permutations
import json
import math
from pathlib import Path
import random

import torch
from actor import InstructionActor
from history import load


def set_objective(actor,catalog,snapshot):
    mem=actor.memory(catalog,snapshot)
    targets=snapshot.targets
    lanes=actor.lanes.num_embeddings
    if len(targets)>lanes:
        raise ValueError(f'{len(targets)} teacher actions exceed the {lanes} simultaneous lanes')
    costs=[]
    for lane in range(lanes):
        h,rules,logits=actor.actions(catalog,mem,lane)
        nll=-logits.log_softmax(0)
        row=[]
        for rid,parents in targets:
            _,losses=actor.references(catalog,mem,h,rid,parents)
            row.append(nll[1+rules.index(rid)]+sum(losses))
        row.extend([nll[0]]*(lanes-len(targets)))
        costs.append(torch.stack(row))
    cost=torch.stack(costs)
    # Exact marginal over injective assignments of unordered targets to lanes.
    # The remaining lanes stop. Identical permutations of stop are counted once.
    orders=[taken+tuple(sorted(set(range(lanes))-set(taken)))
            for taken in permutations(range(lanes),len(targets))]
    picks=torch.tensor(orders,dtype=torch.long,device=cost.device)
    joint=-cost[picks,torch.arange(lanes,device=cost.device)].sum(-1)
    return -joint.logsumexp(0)/lanes


def train(root, output, seed, steps, event_fraction, field_pointer=False, device=None, initial_weights=None):
    if not (0 <= event_fraction <= 1) or steps<=0:
        raise ValueError('bad training options')
    torch.manual_seed(seed)
    rng=random.Random(seed)
    device=device or ('cuda' if torch.cuda.is_available() else 'mps')
    if device=='cpu':
        torch.set_num_threads(1)
    actor=InstructionActor(field_pointer=field_pointer).to(device)
    if initial_weights is not None:
        actor.load_state_dict(torch.load(initial_weights,map_location=device,weights_only=True))
    opt=torch.optim.AdamW(actor.parameters(),lr=.002)
    manifest=json.loads((root/'manifest.json').read_bytes())
    examples=[r for r in manifest if r['split']=='train']
    if not examples:
        raise ValueError('no training programs')
    all_samples, event_samples=[],[]
    # Refresh the opaque IDs and port order on every pass over the corpus.
    def refresh():
        all_samples.clear()
        event_samples.clear()
        for record in examples:
            cat,frames=load(root/record['directory'],rng.getrandbits(64))
            for s in frames:
                all_samples.append((cat,s))
                events={p.address for p in s.ports if p.kind=='repair'}
                if any(events.intersection(refs) for _,refs in s.targets):
                    event_samples.append((cat,s))
        if not event_samples:
            raise ValueError('missing repair supervision')
    mixed=any(r.get('origin')=='eggcc' for r in examples)
    inputs=batches(root,manifest,actor.lanes.num_embeddings,seed) if mixed else None
    seen_programs=set()
    seen_runs=set()
    trained=Counter()
    workloads=Counter()
    trajectory=[]
    for step in range(steps):
        if inputs is None:
            if step%len(examples)==0:
                refresh()
            items=event_samples if rng.random()<event_fraction else all_samples
            cat,s=rng.choice(items)
        else:
            record,cat,s,total=next(inputs)
            seen_programs.add(record['directory'])
            seen_runs.add((record['directory'],s.run))
            trained[record['origin']]+=1
            if record['origin']=='eggcc':
                workloads[record['workload']]+=1
        loss=set_objective(actor,cat,s)
        opt.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(actor.parameters(),2.)
        opt.step()
        if step==0 or (step+1)%50==0 or step+1==steps:
            record={'step':step+1,'loss':float(loss.detach().cpu())}
            if not math.isfinite(record['loss']):
                raise ValueError(record)
            trajectory.append(record)
            print(json.dumps(record),flush=True)
    output.parent.mkdir(parents=True,exist_ok=True)
    torch.save(actor.cpu().state_dict(),output)
    output.with_suffix('.training.json').write_text(json.dumps(dict(field_pointer=field_pointer,device=device,steps=steps,seed=seed,
        event_fraction=None if mixed else event_fraction,
        natural_event_frames=None if mixed else len(event_samples),train_frames=None if mixed else len(all_samples),
        mixed_update_steps=trained,native_updates=workloads,
        initial_weights_sha256=hashlib.sha256(initial_weights.read_bytes()).hexdigest() if initial_weights else None,
        distinct_programs=len(seen_programs) if mixed else None,
        distinct_runs=len(seen_runs) if mixed else None,
        templates=sorted({r['merge_family'] for r in examples if 'merge_family' in r}),trajectory=trajectory),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('corpus',type=Path)
    p.add_argument('weights',type=Path)
    p.add_argument('--steps',type=int,default=500)
    p.add_argument('--seed',type=int,default=1703)
    p.add_argument('--event-fraction',type=float,default=.25)
    p.add_argument('--field-pointer',action='store_true')
    p.add_argument('--device',choices=('cpu','mps','cuda'))
    p.add_argument('--initial-weights',type=Path)
    a=p.parse_args()
    train(a.corpus,a.weights,a.seed,a.steps,a.event_fraction,a.field_pointer,a.device,a.initial_weights)
