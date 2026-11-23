"""Supervise a terminal pointer on all named extensions of sampled training prefixes."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import random

import torch
from torch.nn import functional as F

from alternate_proofs import addr, digest
from anchor_set import Domains, FinalParentActor, OpaqueParentActor
from anchor_set_audit import check
from entry_coverage import split_runs
from history import History
from rule_read import load_actor


@torch.no_grad()
def collect(folder, binary, model, fitted, reserved, seed):
    rng=random.Random(seed)
    tape=json.loads((folder/'tape.json').read_bytes())
    requests=defaultdict(list)
    for p in tape['requests']:
        if len(p['parents'])>=2 and p['run'] not in reserved:
            requests[p['run']].append(p)
    runs=(fitted|set(sorted(requests)[:12])) & requests.keys()
    if not runs:
        return [],{}
    cat=model.catalog_type(json.loads((folder/'program.json').read_bytes()))
    history=History(cat,seed)
    nodes=model.template_graph(cat)
    rows=[]
    probes=[]
    verdicts=[]
    counts=Counter()
    def flush():
        if probes:
            native=check(folder,binary,tape,probes)
            for i,(run,token,w,reason) in enumerate(sorted(native['recall_verdicts'],key=lambda v:v[1])):
                if token!=i+1 or run!=probes[i]['run']:
                    raise ValueError('terminal label lost its named request')
                verdicts.append(w if w is not None else -2 if reason=='off_reference' else -1)
                counts['verified' if w is not None else reason]+=1
            probes.clear()

    with (folder/'memory.jsonl').open() as f:
        for line in f:
            raw=json.loads(line)
            snap=history.snapshot(raw,raw['run'] in runs)
            if snap is None:
                continue
            mem=model.memory(cat,snap,nodes)
            dom=Domains(mem)
            index={port.address:i for i,port in enumerate(mem.ports)}
            contexts=set()
            for req in requests[snap.run]:
                rid=req['rule']
                js=[index[history.rename(addr(x['address']))] for x in req['parents']]
                anchor=next(i for i,j in enumerate(js) if not cat.seminaive[rid] or mem.ports[j].version>=mem.rules[rid])
                order=(anchor,*(i for i in range(len(js)) if i!=anchor))
                contexts.add((rid,order,tuple(js[i] for i in order[:-1])))
            chosen=rng.sample(sorted(contexts),min(len(contexts),4))
            counterfactual=set()
            for rid,order,prev in chosen:
                j=rng.randrange(len(prev))
                domain=dom.role(cat,mem,rid,order[0],order[j]).tolist()
                changed=(*prev[:j],rng.choice(domain),*prev[j+1:])
                if (rid,order,changed) not in contexts:
                    counterfactual.add((rid,order,changed))
            for rid,order,prev in chosen+sorted(counterfactual):
                role=order[-1]
                ids=dom.role(cat,mem,rid,order[0],role)
                prefix=torch.tensor([prev])
                base=model.pair_scores(cat,mem,rid,order[:-1],prefix,role,ids)[0]-model.thresholds[2]
                h=model.final_context(cat,mem,rid,prefix,role)
                rows.append((h,mem.keys[ids],base))
                for j in ids.tolist():
                    parents=[None]*len(order)
                    for i,k in zip(order,(*prev,j),strict=True):
                        port=mem.ports[k]
                        alias,pc=port.address
                        parents[i]=dict(address=dict(token=history.inverse[alias],op=pc),version=port.version)
                    probes.append(dict(token=len(probes)+1,run=snap.run,rule=rid,parents=parents))
                    if len(probes)==16384:
                        flush()
            counts['teacher_prefixes']+=len(chosen)
            counts['perturbed_prefixes']+=len(counterfactual)
            if snap.run==max(runs):
                break
    flush()
    result=[]
    index=0
    for context,keys,base in rows:
        labels=verdicts[index:index+len(keys)]
        index+=len(keys)
        groups=defaultdict(list)
        for j,label in enumerate(labels):
            groups[label].append(j)
        negatives=groups.pop(-1,[])
        groups.pop(-2,None)
        if groups or negatives:
            result.append((context,keys,base,list(groups.values()),negatives))
    if index!=len(verdicts):
        raise ValueError('native labels differ from matrix dimensions')
    return result,dict(runs=sorted(runs),counts=counts)


def fit(root,binary,initial,out,seed,opaque=False):
    torch.manual_seed(seed)
    torch.set_num_threads(1)
    rng=random.Random(seed)
    base=load_actor(initial,True)
    kind=OpaqueParentActor if opaque else FinalParentActor
    model=kind(base.vocabulary,base.name_mode)
    missing,extra=model.load_state_dict(base.state_dict(),strict=False)
    if set(missing)!={'final_query.weight','final_query.bias'} or extra:
        raise ValueError('wrong frozen model')
    selected,fitted,held=split_runs(root,seed)
    pools=defaultdict(list)
    exposure={}
    for rec,_ in selected:
        name=rec['directory']
        if rec['split']!='train':
            raise ValueError('held data entered training')
        rows,stats=collect(root/name,binary,model,{r for n,r in fitted if n==name},
                           {r for n,r in held if n==name},seed+rec['seed'])
        exposure[name]=stats
        for h,k,z,good,bad in rows:
            pools[rec['origin']].append((h.to('mps'),k.to('mps'),z.to('mps'),
                [torch.tensor(g,device='mps') for g in good],torch.tensor(bad,device='mps',dtype=torch.long)))
    model.to('mps')
    opt=torch.optim.AdamW(model.final_query.parameters(),lr=.001)
    origins=sorted(pools)
    used=Counter()
    for _ in range(512):
        loss=[]
        for origin in origins:
            for h,k,z,good,bad in rng.choices(pools[origin],k=2):
                scores=z+model.final_adjustment(h,k)[0]
                if good:
                    best=torch.stack([scores[g].amax() for g in good])
                    loss.append(2*F.softplus(-best).mean())
                    # Pay for the other high-probability proofs of each same winner.
                    redundant=[(scores[g].sigmoid().sum()-best[j].sigmoid()) for j,g in enumerate(good)]
                    loss.append(.1*torch.stack(redundant).mean())
                if len(bad):
                    hard=scores[bad].topk(min(len(bad),max(1,len(good)))).values
                    loss.append(F.softplus(hard).mean())
                used[origin]+=1
        opt.zero_grad(set_to_none=True)
        value=torch.stack(loss).sum()/(2*len(origins))
        if not value.isfinite():
            raise ValueError('non-finite native pointer loss')
        value.backward()
        torch.nn.utils.clip_grad_norm_(model.final_query.parameters(),3.)
        opt.step()
    model.cpu()
    if any(not torch.equal(v,model.state_dict()[n]) for n,v in base.state_dict().items()):
        raise ValueError('upstream policy changed')
    out.mkdir(parents=True,exist_ok=True)
    torch.save(dict(format='opaque-parent-v1' if opaque else 'final-parent-v1',names=model.name_mode,vocabulary=list(model.vocabulary),
                    parameters=model.state_dict()),out/'model.pt')
    result=dict(initial_sha256=digest(initial),weights_sha256=digest(out/'model.pt'),receiver_sha256=digest(binary),
                device='mps',opaque_class_content=opaque,seed=seed,updates=512,training_prefixes={k:len(v) for k,v in pools.items()},
                optimizer_prefix_reads=used,source_exposure=exposure)
    (out/'training.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['training_prefixes'],used,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('root','binary','initial','out'):p.add_argument(name,type=Path)
    p.add_argument('--seed',type=int,default=1703)
    p.add_argument('--opaque',action='store_true',help='omit opaque column codes from address-local content')
    a=p.parse_args()
    fit(a.root,a.binary,a.initial,a.out,a.seed,a.opaque)
