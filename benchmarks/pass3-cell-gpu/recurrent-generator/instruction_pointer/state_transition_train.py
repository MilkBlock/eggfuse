"""Exposure-matched CE on full teacher prefixes vs native autonomous forks."""

import os
import pickle
import random
from collections import defaultdict

import torch

from cell_kv_runtime import native
from competition_corpus import audit
from competition_egg import network
from partner_index_worlds import args
from selected_cell_study import store
from state_transition_corpus import folder, world


def teacher_data(a, w, i):
    p = folder(a) / f"teacher-{i}.pkl"
    if not p.exists():
        data = []
        for s, _ in native(a, w, teacher="higher"):
            v, _ = audit(a, w, s)
            if v:
                data.append((s, v))
        p.write_bytes(pickle.dumps(data))
    return pickle.loads(p.read_bytes())


def train(a, mode, seed):
    net = network(a, "B", seed).train()
    rng = random.Random(seed + 919)
    pools = []
    for i in range(12):
        w = world(a, net.actor, i, True)
        if mode == "teacher":
            data = [(s, v, "teacher") for s, v in teacher_data(a, w, i)]
        else:
            raw = pickle.loads((folder(a) / f"train-{i}.pkl").read_bytes())
            data = []
            for key, row in raw["states"].items():
                valid = {
                    t: l["gain"] for t, l in row["labels"].items() if l["positive"]
                }
                if valid:
                    data.append(
                        (
                            row["state"],
                            valid,
                            "rollout" if key in raw["autonomous"] else "fork",
                        )
                    )
        pools.append((w, data))
    opt = torch.optim.AdamW(
        [p for p in net.parameters() if p.requires_grad], lr=0.001, weight_decay=0
    )
    counts = defaultdict(int)
    curve = []
    for step in range(420):
        losses = []
        for _ in range(2):
            w, data = rng.choice(pools)
            s, v, source = rng.choice(data)
            net.prepare(w)
            m = net.state(w, s)
            effects = defaultdict(list)
            for token, gain in v.items():
                effects[gain].append(token)
            targets = [rng.choice(effects[g]) for g in rng.choices(list(effects), k=8)]
            cache = {t: net.token_loss(w, m, t) for t in set(targets)}
            losses.extend(cache[t] for t in targets)
            counts[source] += len(targets)
        loss = torch.stack(losses).mean()
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(net.parameters(), 3)
        opt.step()
        if step % 30 == 0 or step == 419:
            curve.append((step + 1, float(loss.detach()), dict(counts)))
    torch.save(net.state_dict(), folder(a) / f"{mode}-{seed}.pt")
    store(folder(a) / f"{mode}-{seed}-curve.json", curve)


def load(a, mode, seed):
    net = network(a, "B", seed)
    if mode != "frozen":
        net.load_state_dict(
            torch.load(folder(a) / f"{mode}-{seed}.pt", weights_only=True)
        )
    return net.eval()


if __name__ == "__main__":
    torch.set_num_threads(1)
    a = args()
    for seed in (71, 113):
        train(a, os.environ["TRANS_ARM"], seed)
