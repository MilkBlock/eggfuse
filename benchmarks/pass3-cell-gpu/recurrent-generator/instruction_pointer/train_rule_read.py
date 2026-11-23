"""Paired Metal training of two rule heads over the same frozen checkpoint and Run sets."""
import argparse
from collections import Counter
from dataclasses import dataclass
import hashlib
from itertools import permutations
import json
from pathlib import Path
import random

import torch
from torch.nn.utils.rnn import pad_sequence

from actor import InstructionActor
from history import stream
from rule_read import RuleReadActor


@dataclass
class Example:
    features: dict
    lanes: torch.Tensor
    baseline: torch.Tensor
    target: list


@torch.no_grad()
def capture(root, models, seed):
    examples = []
    sources = Counter()
    manifest = json.loads((root/'manifest.json').read_bytes())
    actor = models['typed']
    rng = random.Random(seed)
    for rec in manifest:
        if rec['split'] != 'train':
            continue
        nodes = None
        for cat, snapshot in stream(root / rec['directory'], rng.getrandbits(62)):
            if nodes is None:
                nodes = actor.template_graph(cat)
            mem = actor.memory(cat, snapshot, nodes)
            rules = list(mem.rules)
            h = actor.lanes.weight
            if len(mem.keys):
                h = actor.next_read(mem.keys.mean(0).expand_as(h), h)
            baseline = torch.stack([InstructionActor.action_logits(actor,cat,mem,lane,rules)[2] for lane in h])
            inputs = {'typed': mem.rule_inputs, 'global': models['global'].rule_inputs(cat, mem)}
            indices = {rid:i+1 for i,rid in enumerate(rules)}
            examples.append(Example(inputs, h, baseline, [indices[r] for r, _ in snapshot.targets]))
            sources[rec['origin']] += 1
    return examples, sources


def update(models, opts, samples, rng, orders, device):
    n = len(samples)
    lanes = orders.shape[1]
    states = torch.stack([s.lanes for s in samples]).to(device)
    base = pad_sequence([s.baseline.T for s in samples], batch_first=True,
                        padding_value=-torch.inf).transpose(1, 2).to(device)
    targets = []
    for s in samples:
        chosen = rng.sample(s.target, min(lanes, len(s.target)))
        targets.append(chosen + [0] * (lanes - len(chosen)))
    target = torch.tensor(targets, device=device)
    batch = torch.arange(n, device=device)[:, None, None]
    lane = torch.arange(lanes, device=device)[None, None, :]
    loss_by_arm = {}
    for mode, model in models.items():
        x = pad_sequence([s.features[mode] for s in samples], batch_first=True).to(device)
        residual = model.correction(x, states)
        logits = torch.cat((base[..., :1], base[..., 1:] + residual), -1)
        logp = logits.log_softmax(-1)
        terms = logp[batch, lane, target[:, orders]]
        # Repeated target rule labels create equal permutations. Their constant
        # multiplicity has zero gradient; log-mean keeps the reported loss nonnegative.
        joint = terms.sum(-1)
        loss = -(joint.logsumexp(1) - torch.tensor(len(orders), device=device).log()).mean() / lanes
        opts[mode].zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad], 2.)
        opts[mode].step()
        loss_by_arm[mode] = float(loss.detach().cpu())
    return loss_by_arm


def train(root, checkpoint, out, epochs, seed, device):
    if epochs < 1:
        raise ValueError('expected at least one epoch')
    torch.set_num_threads(1)
    models = {}
    state = torch.load(checkpoint, weights_only=True, map_location='cpu')
    for mode in ('typed', 'global'):
        torch.manual_seed(seed)
        model = RuleReadActor(mode)
        diff = model.load_state_dict(state, strict=False)
        trainable = {name for name, p in model.named_parameters() if name.startswith('read_')}
        if set(diff.missing_keys) != trainable or diff.unexpected_keys:
            raise ValueError('base weights differ from the frozen Actor')
        for name, p in model.named_parameters():
            p.requires_grad_(name in trainable)
        models[mode] = model
    examples, sources = capture(root, models, seed)
    print('captured', dict(sources), flush=True)
    opts = {}
    for mode, model in models.items():
        model.to(device)
        opts[mode] = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=.003)
    lanes = model.lanes.num_embeddings
    orders = torch.tensor(list(permutations(range(lanes))), device=device)
    rng = random.Random(seed)
    steps = 0
    for epoch in range(epochs):
        rng.shuffle(examples)
        for i in range(0,len(examples),32):
            loss = update(models,opts,examples[i:i+32],rng,orders,device)
            if not all(torch.isfinite(torch.tensor(v)) for v in loss.values()):
                raise ValueError(f'non-finite loss: {loss}')
            steps += 1
        print('epoch', epoch + 1, 'steps', steps, 'last loss', loss, flush=True)
    out.mkdir(exist_ok=True,parents=True)
    for mode, model in models.items():
        saved = model.cpu().state_dict()
        if any(not torch.equal(saved[k], v) for k,v in state.items()):
            raise ValueError('base Actor changed')
        torch.save(dict(format='rule-read-v1',read_mode=mode,parameters=saved),out/f'{mode}.pt')
    (out/'training.json').write_text(json.dumps(dict(epochs=epochs, steps_per_arm=steps,
        training_runs=sources, device=device, seed=seed, batch_size=32,
        base_checkpoint_sha256=hashlib.sha256(checkpoint.read_bytes()).hexdigest()),indent=2)+'\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('root','weights','output'):
        p.add_argument(name,type=Path)
    p.add_argument('--epochs',type=int,default=4)
    p.add_argument('--seed',type=int,default=1703)
    p.add_argument('--device',choices=('mps','cpu'),default='mps')
    a = p.parse_args()
    train(a.root,a.weights,a.output,a.epochs,a.seed,a.device)
