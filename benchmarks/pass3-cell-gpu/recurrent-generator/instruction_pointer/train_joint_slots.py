"""Fit complete requests from sealed EggCC snapshots with unordered set supervision."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import random

import torch
from torch.nn import functional as F

from alternate_proofs import digest
from anchor_set import Domains
from history import History, address
from joint_slots import JointSlots, rule_inputs
from rule_read import load_actor


def collect(folder, actor, seed, limit):
    rng = random.Random(seed)
    catalog = actor.catalog_type(json.loads((folder/'program.json').read_bytes()))
    by_run = defaultdict(lambda: defaultdict(list))
    for req in json.loads((folder/'tape.json').read_bytes())['requests']:
        by_run[req['run']][req['rule']].append(req)
    with torch.no_grad():
        nodes = actor.template_graph(catalog)
        history = History(catalog,seed,cache_ports=True)
        busy = sorted(r for r,rules in by_run.items() if any(len(catalog.atoms[rid])>=2 for rid in rules))
        sample = set(rng.sample(busy,min(limit,len(busy))))
        examples=[]
        with (folder/'memory.jsonl').open() as stream:
            for line in stream:
                frame=json.loads(line)
                snap=history.snapshot(frame,frame['run'] in sample)
                if snap is None: continue
                mem=actor.memory(catalog,snap,nodes)
                dom=Domains(mem)
                active=list(by_run[snap.run])
                negatives=sorted(set(snap.rules)-set(active))
                for rid in active+rng.sample(negatives,min(len(negatives),len(active))):
                    prepared=rule_inputs(catalog,mem,dom,rid)
                    if prepared is None:continue
                    inputs,ids=prepared
                    indexes=[{mem.ports[int(j)].address:k for k,j in enumerate(domain.tolist())} for domain in ids]
                    targets=[[idx[history.rename(address(p['address']))] for idx,p in zip(indexes,q['parents'],strict=True)]
                             for q in by_run[snap.run][rid]]
                    examples.append((inputs,targets))
        return examples


def loss(logits, stop, targets):
    if not targets:return F.softplus(-stop).mean()
    n=len(targets)
    cost=F.softplus(stop)[:,None].expand(-1,n)
    target=torch.tensor(targets,dtype=torch.long,device=stop.device)
    for role,score in enumerate(logits):
        cost=cost-score.log_softmax(-1)[:,target[:,role]]
    if n<len(stop):
        cost=torch.cat((cost,F.softplus(-stop)[:,None].expand(-1,len(stop)-n)),1)
    # Balanced soft assignment gives each reference binding a share of the loss.
    with torch.no_grad():
        match=-cost.detach()/.2
        for _ in range(20):
            match=match-match.logsumexp(1,keepdim=True)
            match=match-match.logsumexp(0,keepdim=True)
    return (match.exp()*cost).sum()/cost.shape[1]


def device_inputs(inputs,device):
    root,roles,keys,fields,fresh,wiring=inputs
    return (root.to(device),*[[x.to(device) for x in xs] for xs in (roles,keys,fields,fresh)],wiring)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('root','weights','output'):p.add_argument(key,type=Path)
    p.add_argument('--steps',type=int,default=600)
    p.add_argument('--rounds',type=int,default=2)
    p.add_argument('--runs',type=int,default=64)
    a=p.parse_args()
    torch.set_num_threads(1)
    seed=81017
    torch.manual_seed(seed)
    rng=random.Random(seed)
    actor=load_actor(a.weights,True)
    examples=[]
    for i,name in enumerate(('sum','dot')):
        examples.extend(collect(a.root/name,actor,seed+i,a.runs))
    positive=[ex for ex in examples if ex[1]]
    negative=[ex for ex in examples if not ex[1]]
    device='mps'
    model=JointSlots(actor.width,16).to(device)
    opt=torch.optim.AdamW(model.parameters(),lr=.002)
    for i in range(a.steps):
        inputs,targets=rng.choice(negative if negative and i%4==0 else positive)
        scores,stop=model(*device_inputs(inputs,device),a.rounds)
        obj=loss(scores,stop,targets)
        opt.zero_grad();obj.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(),1.)
        opt.step()
    torch.mps.synchronize()
    a.output.mkdir(parents=True,exist_ok=True)
    torch.save(model.cpu().state_dict(),a.output/'head.pt')
    (a.output/'training.json').write_text(json.dumps(dict(seed=seed,steps=a.steps,rounds=a.rounds,proposals=16,
        programs=['sum','dot'],positive=len(positive),negative=len(negative),base=digest(a.weights),
        head=digest(a.output/'head.pt'),device=device),indent=2)+'\n')
