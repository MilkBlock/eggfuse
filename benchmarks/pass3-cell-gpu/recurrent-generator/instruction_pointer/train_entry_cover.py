"""Give each observed training entry a positive root read and one complete supervised parent path."""
import argparse
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path
import random

import torch

from alternate_proofs import digest,mine
from entry_coverage import entries,split_runs
from history import stream
from rule_read import load_actor
from train_anchor_set import targets,reads,objective


def collect(root,plan,initial_labels,binary,model,seed):
    selected,fitted,held=split_runs(root,seed)
    extra=plan['additional']
    frames=[]
    families=defaultdict(list)
    counts=Counter()
    for rec,_ in selected:
        if rec['origin']!='eggcc':continue
        name=rec['directory']
        folder=root/name
        runs={r for n,r in fitted if n==name}
        supplement=set(extra.get(name,[]))
        if any((name,r) in held or r in runs for r in supplement):raise ValueError('invalid supplement')
        additional=mine(folder,binary,supplement)
        counts.update(additional['counts'])
        original=initial_labels['programs'][name]
        if any(original[k]!=additional[k] for k in ('program_sha256','teacher_sha256','memory_sha256')):
            raise ValueError('different program trajectory')
        needed=runs|supplement
        proofs=[p for p in original['proofs']+additional['proofs'] if p['run'] in needed]
        extra_ids=defaultdict(list)
        for p in proofs:extra_ids[p['run']].append(p['winner'])
        classified=entries(folder)
        domain=model.catalog_type
        reference=stream(folder,seed+rec['seed'],needed,domain)
        alternatives=stream(folder,seed+rec['seed'],needed,domain,proofs)
        for (cat,s),(_,alt) in zip(reference,alternatives,strict=True):
            if not s.targets:continue
            if s.run!=alt.run or [p.address for p in s.ports]!=[p.address for p in alt.ports]:
                raise ValueError('inconsistent supervision')
            labels=classified[s.run]
            owner_ids=[i for _,i in labels]+extra_ids[s.run]
            all_credit=targets(cat,s,s.targets+alt.targets,owner_ids)
            base=targets(cat,s)
            frame=len(frames)
            frames.append((cat,s,*base,all_credit))
            addr={p.address:i for i,p in enumerate(s.ports)}
            for (signature,_),(rid,refs) in zip(labels,s.targets,strict=True):
                anchor=signature[1]
                order=[] if anchor is None else [anchor]+[j for j in range(len(refs)) if j!=anchor]
                prefixes=[(rid,anchor,tuple(addr[refs[j]] for j in order[:k])) for k in range(1,len(order))]
                families[signature].append((frame,((rid,anchor),prefixes)))
    if len(families)!=plan['entries_after']:raise ValueError('unrepresented positive training entry')
    return frames,families,counts


def train(root,plan_file,labels,binary,initial,out,seed):
    torch.manual_seed(seed);torch.set_num_threads(1)
    rng=random.Random(seed)
    plan=json.loads(plan_file.read_bytes())
    proofs=json.loads(labels.read_bytes())
    if proofs['seed']!=seed or plan['seed']!=seed or proofs['receiver_sha256']!=digest(binary):
        raise ValueError('unmatched native labels')
    model=load_actor(initial,True)
    frozen=model.state_dict()
    frames,families,native=collect(root,plan,proofs,binary,model,seed)
    for name,p in model.named_parameters():
        p.requires_grad_(name.startswith(('anchor_query.','anchor_key.','anchor_bias.','pair_query.',
                                          'pair_key.','pair_bias.','field_comparison.','next_read.')))
    trained={name for name,p in model.named_parameters() if p.requires_grad}
    # Keep the original reference weights off device for the frozen-state check.
    frozen={n:v.clone() for n,v in frozen.items() if n not in trained}
    model.to('mps')
    opt=torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],lr=.001)
    sequence=list(families)
    rng.shuffle(sequence)
    counts=Counter()
    for family in sequence:
        frame,focus=rng.choice(families[family])
        cat,s,roots,children,credit=frames[frame]
        mem=model.memory(cat,s)
        terms=reads(cat,s,mem,model,roots,children,rng,credit,focus=focus)
        parts=[objective(scores-model.thresholds[level],ids,pos,owners)
               for level,scores,ids,pos,owners in terms if scores.requires_grad]
        counts['entry_reads']+=1
        counts['required_prefix_reads']+=len(focus[1])
        if not parts:continue
        loss=torch.stack(parts).mean()
        if not loss.isfinite():raise ValueError('nonfinite focused training')
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(),3.)
        opt.step()
        counts['updates']+=1
    result=model.cpu().state_dict()
    if any(not torch.equal(result[n],v) for n,v in frozen.items()):raise ValueError('frozen representation changed')
    out.mkdir(exist_ok=True,parents=True)
    torch.save(dict(format='parallel-anchor-v1',names=model.name_mode,vocabulary=list(model.vocabulary),
                    parameters=result),out/'model.pt')
    record=dict(device='mps',seed=seed,counts=counts,positive_snapshots=len(frames),native_extra=native,
        frozen_sha256=digest(initial),weights_sha256=digest(out/'model.pt'),plan_sha256=digest(plan_file),
        labels_sha256=digest(labels),receiver_sha256=digest(binary))
    (out/'training.json').write_text(json.dumps(record,indent=2)+'\n')
    print(counts,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('root','plan','labels','receiver','initial','out'):p.add_argument(k,type=Path)
    p.add_argument('--seed',type=int,default=1703)
    a=p.parse_args();train(a.root,a.plan,a.labels,a.receiver,a.initial,a.out,a.seed)
