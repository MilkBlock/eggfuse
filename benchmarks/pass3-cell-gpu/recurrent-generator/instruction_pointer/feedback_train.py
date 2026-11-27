"""Complete-token CE; matched target streams for a receipt-visible and blind policy."""

import os
import pickle
import random
from collections import defaultdict

import torch

from competition_corpus import out
from competition_corpus import world as old_world
from feedback_data import public
from feedback_stall import folder
from partner_index_worlds import args
from selected_cell_study import store
from state_transition_corpus import world
from state_transition_train import load


def get(a, arm, seed):
    net = load(a, "transition", seed)
    if arm != "old":
        net.load_state_dict(
            torch.load(folder(a) / f"{arm}-{seed}.pt", weights_only=True)
        )
    return net


def train(a, arm, seed):
    net = load(a, "transition", seed).train()
    pools = defaultdict(list)
    for i in range(12):
        w = world(a, net.actor, i, True)
        d = pickle.loads((folder(a) / f"train-{i}.pkl").read_bytes())
        pools["transition"].extend((w, s, v) for s, v in d["trans"])
        pools["submit"].extend((w, s, v) for s, v, _, _ in d["mids"])
        for s, v in d["siblings"]:
            # Verified Higher trajectories from both alternate producers.
            pools["siblings"].append(
                (w, s, {t: g for t, g in v.items() if t[0] >= w.primitives})
            )
        base = old_world(a, net.actor, "single", i, True)
        for s, ts, v, n in pickle.loads(
            (out(a) / f"train-single-{i}.pkl").read_bytes()
        ):
            pools["base"].append((base, s, v))
    opt = torch.optim.AdamW(
        [v for v in net.parameters() if v.requires_grad], lr=0.001, weight_decay=0
    )
    rng = random.Random(seed + 2026)
    curve = []
    for step in range(420):
        losses = []
        for items in pools.values():
            w, s, v = rng.choice(items)
            net.prepare(w)
            m = net.state(w, s if arm == "visible" else public(s))
            groups = defaultdict(list)
            for t, g in v.items():
                groups[g].append(t)
            targets = [rng.choice(groups[g]) for g in rng.choices(list(groups), k=4)]
            scores = {t: net.token_loss(w, m, t) for t in set(targets)}
            losses.extend(scores[t] for t in targets)
        ce = torch.stack(losses).mean()
        opt.zero_grad(set_to_none=True)
        ce.backward()
        torch.nn.utils.clip_grad_norm_(net.parameters(), 3)
        opt.step()
        if step % 30 == 0 or step == 419:
            curve.append([step + 1, float(ce.detach()), (step + 1) * 16])
    torch.save(net.state_dict(), folder(a) / f"{arm}-{seed}.pt")
    store(folder(a) / f"curve-{arm}-{seed}.json", curve)


if __name__ == "__main__":
    torch.set_num_threads(1)
    a = args()
    for seed in (71, 113):
        train(a, os.environ["FB_ARM"], seed)
