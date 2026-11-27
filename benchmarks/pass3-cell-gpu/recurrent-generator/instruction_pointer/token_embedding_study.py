"""Controlled full-token CE, native post-freeze Bake and independent execution."""

import hashlib
import json
import os
from pathlib import Path

import numpy as np
import torch

from cell_kv_probes import swap_addresses
from cell_kv_runtime import native
from cell_kv_study import digest, groups, names, vector
from cell_kv_world import World, make
from partner_index_worlds import args
from rule_read import load_actor
from token_embedding import TokenEmbedding

VARIANTS = ("current", "structure", "mixed", "interface")
SEEDS = (71, 113)
UPDATES = 360


def save(path, obj):
    path.write_text(json.dumps(obj, separators=(",", ":")) + "\n")


def initial():
    path = (
        Path(os.environ["ARTIFACT_ROOT"]) / "cell-kv-fullread/weights/C-joint-71-360.pt"
    )
    return torch.load(path, weights_only=True, map_location="cpu")


def fixed_digest(net):
    h = hashlib.sha256()
    for name, p in net.named_parameters():
        if not p.requires_grad:
            h.update(name.encode())
            h.update(p.detach().numpy().tobytes())
    return h.hexdigest()


def fitworlds(a):
    actor = load_actor(a.actor, True)
    return {
        name: World(make(a, name, depth, jobs, seed, common=True), actor)
        for name, depth, jobs, seed in names("train")
    }


def prepare(a):
    rows = {}
    for name, w in fitworlds(a).items():
        rows[name] = native(a, w, teacher="primitive") + native(a, w, teacher="higher")
    torch.save(rows, a.out / "training.pt")


def weights(a, v, seed):
    return a.out / f"{v}-{seed}.pt"


def train(a):
    worlds = fitworlds(a)
    rows = torch.load(a.out / "training.pt", weights_only=False)
    for seed in SEEDS:
        for variant in VARIANTS:
            rng = np.random.default_rng(seed)
            net = TokenEmbedding(a, variant, initial()).train()
            fixed = fixed_digest(net)
            layers = dict(groups(net), age=[net.actor.age])
            start = {k: vector(v) for k, v in layers.items()}
            grads = dict.fromkeys(layers, 0.0)
            opt = torch.optim.AdamW(
                filter(lambda p: p.requires_grad, net.parameters()),
                lr=0.0015,
                weight_decay=0.0,
            )
            losses = []
            for step in range(UPDATES):
                eligible = [
                    n for n, _, j, _ in names("train") if step >= UPDATES // 3 or j <= 2
                ]
                name = rng.choice(eligible)
                w = worlds[name]
                net.prepare(w)
                terms = []
                for i in rng.choice(len(rows[name]), 3):
                    state, targets = rows[name][i]
                    m = net.state(w, state)
                    for j in rng.choice(len(targets), 2):
                        terms.append(net.token_loss(w, m, targets[j]))
                loss = torch.stack(terms).mean()
                opt.zero_grad(set_to_none=True)
                loss.backward()
                for k, mod in layers.items():
                    grads[k] += float(vector(mod, grad=True).norm())
                torch.nn.utils.clip_grad_norm_(net.parameters(), 3.0)
                opt.step()
                losses.append(float(loss.detach()))
            assert fixed_digest(net) == fixed
            path = weights(a, variant, seed)
            torch.save(net.state_dict(), path)
            save(
                path.with_suffix(".json"),
                {
                    "variant": variant,
                    "seed": seed,
                    "frozen_sha256": fixed,
                    "registered": sum(p.numel() for p in net.parameters()),
                    "trainable": sum(
                        p.numel() for p in net.parameters() if p.requires_grad
                    ),
                    "ce60": [np.mean(chunk) for chunk in np.array_split(losses, 6)],
                    "groups": {
                        k: {
                            "n": start[k].numel(),
                            "mean_grad": grads[k] / UPDATES,
                            "movement": float((vector(v) - start[k]).norm()),
                        }
                        for k, v in layers.items()
                    },
                },
            )
            print(variant, seed, np.mean(losses[-60:]), flush=True)


def held(a):
    # All weights must exist before generating held-out Recipe layouts.
    for seed in SEEDS:
        for v in VARIANTS:
            if not weights(a, v, seed).is_file():
                raise RuntimeError("complete all training before Bake")
    fit = fitworlds(a)
    train = {h for w in fit.values() for h in digest(w)}
    prior = json.loads(Path("run-recall/cell-kv/manifest.json").read_text())
    train.update(
        h for p in prior["programs"] if p["split"] == "train" for h in p["signatures"]
    )
    actor = load_actor(a.actor, True)
    for i, (depth, jobs, fork) in enumerate(
        [(5, 1, False), (7, 1, True), (5, 3, True), (7, 4, False)]
    ):
        for flip in (False, True):
            name = f"post-{i}-{int(flip)}"
            w = World(
                make(a, name, depth, jobs, 873015 + i * 71, fork, flip, True), actor
            )
            assert not train.intersection(digest(w))
            root_end = [
                (w.roles[body[0][0]], w.outputs[body[0][0]], w.outputs[body[-1][0]])
                for body in w.layouts[-2:]
            ]
            assert root_end[0] == root_end[1]
            yield w


@torch.no_grad()
def evaluate(a, trained=True):
    rows, prob = [], []
    for w in held(a):
        state, targets = native(a, w, teacher="higher")[0]
        valid = [(tid, refs) for tid, refs in targets if tid >= w.primitives]
        configs = [(v, seed) for seed in (SEEDS if trained else (0,)) for v in VARIANTS]
        for draw in (193, 827):
            for block in (0, 1):
                for v, seed in (
                    configs if (block + (draw == 827)) % 2 == 0 else reversed(configs)
                ):
                    net = TokenEmbedding(a, v, initial()).eval()
                    if trained:
                        net.load_state_dict(
                            torch.load(weights(a, v, seed), weights_only=True)
                        )
                    r = native(a, w, policy=net, seed=draw)
                    rows.append(
                        dict(
                            case=w.dir.name, v=v, seed=seed, draw=draw, block=block, **r
                        )
                    )
                    if block == 0 and draw == 193:
                        m = net.state(w, state)
                        moved = net.state(w, swap_addresses(state))
                        for tid, refs in valid:
                            lp = m["lp"][m["menu"].index(tid)]
                            paddr = net.address(w, m, tid, []).exp()
                            bind = paddr[m["pos"][refs[0]]]
                            alt = 2 * w.primitives + 1 - tid
                            err = max(
                                float((moved["lp"].exp() - m["lp"].exp()).abs().max()),
                                float(
                                    (
                                        net.address(w, moved, tid, []).exp().flip((0,))
                                        - paddr
                                    )
                                    .abs()
                                    .max()
                                ),
                            )
                            prob.append(
                                {
                                    "case": w.dir.name,
                                    "v": v,
                                    "seed": seed,
                                    "tid": tid,
                                    "p_template": float(lp.exp()),
                                    "correct_vs_other": float(
                                        torch.sigmoid(
                                            lp - m["lp"][m["menu"].index(alt)]
                                        )
                                    ),
                                    "p_bind": float(bind),
                                    "p_complete": float(lp.exp() * bind),
                                    "perm_error": err,
                                    "structure_distance": float(
                                        (net.cache[1][tid] - net.cache[1][alt]).norm()
                                    ),
                                }
                            )
        print("native", w.dir.name, len(rows), flush=True)
        save(a.out / ("native.json" if trained else "before-native.json"), rows)
        save(a.out / ("prob.json" if trained else "before-prob.json"), prob)


if __name__ == "__main__":
    torch.set_num_threads(1)
    a = args()
    {
        "prepare": prepare,
        "train": train,
        "live": evaluate,
        "evaluate": lambda a: evaluate(a, trained=False),
    }[a.task](a)
