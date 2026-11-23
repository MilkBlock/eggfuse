"""Teacher-force whole Run sets, supervise one terminal Stop and cover distinct wave rules."""
import argparse
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import random

import torch
from torch.nn.utils.rnn import pad_sequence

from history import stream
from rule_read import load_actor
from sequence_actor import SequenceActor


@dataclass
class Run:
    inputs: torch.Tensor
    lanes: torch.Tensor
    base: torch.Tensor
    labels: torch.Tensor
    feedback: torch.Tensor


@torch.no_grad()
def capture(root, model, seed):
    runs = []
    counts = Counter()
    rng = random.Random(seed)
    for rec in json.loads((root/'manifest.json').read_bytes()):
        if rec['split'] != 'train':
            continue
        nodes = None
        for cat,frame in stream(root/rec['directory'],rng.getrandbits(62)):
            if nodes is None:
                nodes = model.template_graph(cat)
            mem = model.memory(cat,frame,nodes)
            inputs,lanes,base = model.setup(cat,frame,mem)
            ids = {r:i+1 for i,r in enumerate(mem.rules)}
            lookup = {p.address:i for i,p in enumerate(mem.ports)}
            labels = torch.tensor([ids[r] for r,_ in frame.targets],dtype=torch.long)
            keys = [model.request_key(cat,mem,r,refs,lookup) for r,refs in frame.targets]
            feedback = torch.stack(keys) if keys else nodes.new_empty((0,model.width))
            if len(labels) and not base[:,labels].isfinite().all():
                raise ValueError('teacher action missing from rule domain')
            runs.append(Run(inputs,lanes,base,labels,feedback))
            counts.update(runs=1,teacher_commits=len(labels),busy=int(bool(keys)),empty=int(not keys),
                          runs_above_lane_budget=int(len(keys)>len(lanes)))
    return runs,counts


def train_batch(model, opt, items, rng, device):
    size = len(items)
    lanes = model.lanes.num_embeddings
    x = pad_sequence([r.inputs for r in items],batch_first=True).to(device)
    states = torch.stack([r.lanes for r in items]).to(device)
    base = pad_sequence([r.base.T for r in items],batch_first=True,padding_value=-torch.inf).transpose(1,2).to(device)
    labels, history = [], []
    for r in items:
        order = list(range(len(r.labels)))
        rng.shuffle(order)
        labels.append(torch.cat((r.labels[order],torch.zeros(1,dtype=torch.long))))
        history.append(torch.cat((r.feedback,r.feedback.new_zeros(1,model.width)))[order+[len(order)]])
    target = pad_sequence(labels,batch_first=True,padding_value=-1).to(device)
    feedback = pad_sequence(history,batch_first=True).to(device)
    # Input at step t is the previous issue. Stop has no successor loss.
    output,_ = model.sequence_history(feedback)
    past = torch.cat((torch.zeros_like(output[:,:1]),output[:,:-1]),dim=1)
    roles = torch.arange(target.size(1),device=device) % lanes
    logits = model.logits(model.sequence_key(x).tanh(),past,states[:,roles],base[:,roles])
    logp = logits.log_softmax(-1)
    valid = target >= 0
    index = target.clamp_min(0).unsqueeze(-1)
    nll = -logp.gather(-1,index).squeeze(-1).masked_fill(~valid,0)
    action_loss = (nll.sum(1)/valid.sum(1)).mean()
    # The product runs only over real issuing positions of this teacher wave.
    log_miss = torch.log1p(-logp.exp().clamp_max(1-1e-6)).masked_fill((target<=0).unsqueeze(-1),0)
    required = torch.zeros_like(logp).scatter_(-1,index,1).masked_fill((target<=0).unsqueeze(-1),0)
    pad = (-target.size(1)) % lanes
    def per_wave(t):
        return torch.nn.functional.pad(t,(0,0,0,pad)).reshape(size,-1,lanes,t.size(-1))
    miss = per_wave(log_miss).sum(2)
    need = per_wave(required).amax(2)
    cover = -torch.log((-miss.expm1()).clamp_min(1e-8))
    coverage_loss = (cover*need).sum()/need.sum().clamp_min(1)
    loss = action_loss + 0.25 * coverage_loss
    if not torch.isfinite(loss):
        raise ValueError('nonfinite sequence objective')
    opt.zero_grad(set_to_none=True)
    loss.backward()
    torch.nn.utils.clip_grad_norm_(model.parameters(),2.)
    opt.step()
    return float(loss.detach().cpu())


def train(root, initial, out, epochs=4, seed=1703):
    torch.set_num_threads(1)
    torch.manual_seed(seed)
    model = SequenceActor()
    old = load_actor(initial,True)
    if not old.mask_anchors:
        raise ValueError('need the masked rule head')
    diff = model.load_state_dict(old.state_dict(),strict=False)
    trained = {n for n,_ in model.named_parameters() if n.startswith('sequence_')}
    if set(diff.missing_keys)!=trained or diff.unexpected_keys:
        raise ValueError('unexpected backbone')
    for n,p in model.named_parameters():
        p.requires_grad_(n in trained)
    runs,source = capture(root,model,seed)
    print('captured',dict(source),flush=True)
    model.to('mps')
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],lr=.003)
    busy = [i for i,r in enumerate(runs) if len(r.labels)]
    empty = [i for i,r in enumerate(runs) if not len(r.labels)]
    rng = random.Random(seed)
    visits = Counter()
    steps = 0
    for epoch in range(epochs):
        # Length buckets limit padding; all teacher requests remain in every selected Run.
        rng.shuffle(busy)
        rng.shuffle(empty)
        ordered = []
        for i in range(0,len(busy),256):
            ordered.extend(sorted(busy[i:i+256],key=lambda j:len(runs[j].labels)))
        batches = [ordered[i:i+16] for i in range(0,len(ordered),16)]
        rng.shuffle(batches)
        for j in range(max(len(batches),math.ceil(len(empty)/16))):
            active = batches[j % len(batches)]
            idle = [empty[(16*j+k)%len(empty)] for k in range(len(active))]
            items = [runs[i] for i in active+idle]
            loss = train_batch(model,opt,items,rng,'mps')
            visits.update(busy=len(active),empty=len(idle),stop=len(items),
                          teacher_issues=sum(len(r.labels) for r in items))
            steps += 1
        print('epoch',epoch+1,'steps',steps,'last loss',loss,flush=True)
    out.mkdir(parents=True,exist_ok=True)
    saved=model.cpu().state_dict()
    if any(not torch.equal(saved[k],v) for k,v in old.state_dict().items()):
        raise ValueError('backbone changed')
    torch.save(dict(format='sequence-actor-v1',parameters=saved),out/'sequence.pt')
    (out/'training.json').write_text(json.dumps(dict(device='mps',epochs=epochs,steps=steps,
        seed=seed,source=source,visits=visits,initial_sha256=hashlib.sha256(initial.read_bytes()).hexdigest()),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('root','initial','out'):
        p.add_argument(name,type=Path)
    p.add_argument('--epochs',type=int,default=4)
    a=p.parse_args()
    train(a.root,a.initial,a.out,a.epochs)
