"""Leave one EggCC program out; plain complete Cell cross entropy."""

import json
import os
import pickle
import random

import torch

from cell_kv_world import World
from competition_egg import egg
from partner_index_worlds import args
from prefix_attention import attach
from prefix_corpus import folder
from variable_completion import network

CASES = ("fact", "loopfact", "sum-divisors")
LAYERS = ("latent", "query", "input_content", "input_role")


def make(a, arm):
    n = network(a, 71)
    n.requires_grad_(False)
    for key in LAYERS:
        getattr(n.actor, key).requires_grad_(True)
    if arm == "rel":
        attach(n)
    return n


def train(a, held, seed, arm):
    n = make(a, arm)
    d = folder(a)
    ds = []
    for case in CASES:
        if case == held:
            continue
        ir, _ = egg(a, case)
        w = World(ir, n.actor, entry_table=None, sides="")
        rows = pickle.loads((d / f"{case}.pkl").read_bytes())
        ds.extend((w, s, r, ts) for s, r, ts, _ in rows if ts)
    rng = random.Random(seed)
    opt = torch.optim.AdamW(
        [p for p in n.parameters() if p.requires_grad], lr=0.001, weight_decay=0
    )
    grads = {}
    curve = []
    losses = []
    for step in range(192):
        w, s, r, targets = rng.choice(ds)
        n.prepare(w)
        m = n.state(w, s)
        ts = rng.sample(targets, min(3, len(targets)))
        loss = torch.stack([n.token_loss(w, m, (r, refs)) for refs in ts]).mean()
        opt.zero_grad(set_to_none=True)
        loss.backward()
        for key, p in n.named_parameters():
            if p.grad is not None:
                grads.setdefault(key, []).append(float(p.grad.norm()))
        torch.nn.utils.clip_grad_norm_(n.parameters(), 2.0)
        opt.step()
        losses.append(float(loss.detach()))
        if (step + 1) % 32 == 0:
            curve.append(sum(losses) / len(losses))
            losses = []
    tag = f"{held}-{arm}-{seed}"
    weights = {k: p.detach() for k, p in n.named_parameters() if p.requires_grad}
    torch.save(weights, d / f"{tag}.pt")
    (d / f"{tag}.json").write_text(
        json.dumps(
            {
                "steps": 192,
                "states": len(ds),
                "targets": sum(len(t) for _, _, _, t in ds),
                "gradient_mean": {k: sum(v) / len(v) for k, v in grads.items()},
                "curve": curve,
            }
        )
    )
    print(tag, curve, flush=True)


def fitted(a, held, arm, seed):
    n = make(a, arm)
    if seed:
        trained = "rel" if arm == "rel_off" else arm
        params = torch.load(
            folder(a) / f"{held}-{trained}-{seed}.pt", weights_only=True
        )
        assert set(params) == {k for k, p in n.named_parameters() if p.requires_grad}
        n.load_state_dict(params, strict=False)
    return n.eval()


if __name__ == "__main__":
    torch.set_num_threads(1)
    a = args()
    for arm in ("rel", "base"):
        for seed in (71, 113):
            train(a, os.environ["TR_CASE"], seed, arm)
