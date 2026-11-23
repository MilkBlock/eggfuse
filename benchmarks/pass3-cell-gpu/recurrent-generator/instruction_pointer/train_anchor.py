"""Matched fine-tuning of a rule head with source-Run anchor domains."""
import argparse
from collections import Counter, defaultdict
from copy import deepcopy
from itertools import permutations
import hashlib
import json
from pathlib import Path
import random

import torch

from actor import InstructionActor
from history import stream
from rule_read import load_actor
from train_rule_read import Example, update


@torch.no_grad()
def examples(root, model, seed):
    rng = random.Random(seed)
    frames = []
    strata = defaultdict(list)
    sources = Counter()
    evidence = Counter()
    for rec in json.loads((root/'manifest.json').read_bytes()):
        if rec['split'] != 'train':
            continue
        nodes = None
        for cat, frame in stream(root/rec['directory'], rng.getrandbits(62)):
            if nodes is None:
                nodes = model.template_graph(cat)
            mem = model.memory(cat, frame, nodes)
            rules = list(mem.rules)
            index = {r:i+1 for i, r in enumerate(rules)}
            labels = [index[r] for r, _ in frame.targets]
            if any(not mem.rule_support[i-1] for i in set(labels)):
                raise ValueError('anchor mask rejected a reference binding')
            h = model.lanes.weight
            if len(mem.keys):
                h = model.next_read(mem.keys.mean(0).expand_as(h), h)
            base = torch.stack([InstructionActor.action_logits(model,cat,mem,lane,rules)[2] for lane in h])
            base[:,1:].masked_fill_(~mem.rule_support, -torch.inf)
            origin = rec['origin']
            for arity in {len(refs) for _, refs in frame.targets}:
                strata[origin, arity].append(len(frames))
            frames.append(Example({'typed':mem.rule_inputs},h,base,labels))
            sources[origin] += 1
            evidence.update(scheduled=len(rules), masked=int((~mem.rule_support).sum()),
                            teacher_bindings=len(labels))
    return frames, strata, sources, evidence


def train(root, initial, out, seed=1703, epochs=4, device='mps'):
    torch.set_num_threads(1)
    model = load_actor(initial, True)
    if model.read_mode != 'typed' or model.mask_anchors or epochs < 1:
        raise ValueError('expected the original typed head and at least one epoch')
    model.mask_anchors = True
    out.mkdir(exist_ok=True,parents=True)
    def save(actor, name):
        torch.save(dict(format='rule-read-v1', read_mode='typed', mask_anchors=True,
                        parameters=actor.cpu().state_dict()),out/f'{name}.pt')
    save(model, 'mask')
    frames,strata,sources,evidence = examples(root,model,seed)
    result = dict(seed=seed,epochs=epochs,device=device,training_runs=sources,mask_audit=evidence,
                  initial_weights_sha256=hashlib.sha256(initial.read_bytes()).hexdigest(),arms={},
                  positive_runs_by_origin_and_arity={f'{k[0]}/{k[1]}':len(v) for k,v in strata.items()})
    for name in ('uniform', 'stratified'):
        # Independent streams keep both arms' natural frame permutation identical.
        shuffler, sampler, labels = (random.Random(seed+i) for i in range(3))
        actor = deepcopy(model).to(device)
        for key,p in actor.named_parameters():
            p.requires_grad_(key.startswith('read_'))
        opt = torch.optim.AdamW([p for p in actor.parameters() if p.requires_grad],lr=.003)
        orders = torch.tensor(list(permutations(range(actor.lanes.num_embeddings))),device=device)
        visits = Counter()
        steps = 0
        ids = list(range(len(frames)))
        for _ in range(epochs):
            shuffler.shuffle(ids)
            for i in range(0,len(ids),32):
                batch = list(ids[i:i+32])
                if name == 'stratified':
                    for j in range(0,len(batch),4):
                        key = sampler.choice(sorted(strata))
                        batch[j] = sampler.choice(strata[key])
                        visits[f'{key[0]}/{key[1]}'] += 1
                loss = update({'typed':actor},{'typed':opt},[frames[j] for j in batch],labels,orders,device)
                if not torch.isfinite(torch.tensor(loss['typed'])):
                    raise ValueError('nonfinite rule loss')
                steps += 1
        save(actor, name)
        if any(not torch.equal(model.state_dict()[k],v) for k,v in actor.state_dict().items()
               if not k.startswith('read_')):
            raise ValueError('frozen backbone changed')
        result['arms'][name] = dict(steps=steps,stratified_draws=visits)
        print(name, steps, flush=True)
    (out/'training.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('root','initial','output'):
        p.add_argument(key,type=Path)
    args = p.parse_args()
    train(args.root,args.initial,args.output)
