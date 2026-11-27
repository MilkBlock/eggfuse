"""Complete Cell CE with crossed freezing on native input counterfactuals."""

import os
from collections import Counter
from pathlib import Path

import numpy as np
import torch

from cell_kv_model import CellKV
from cell_kv_runtime import native
from compatibility_world import cases, world
from partner_index_worlds import args
from rule_read import load_actor
from token_embedding_study import fixed_digest, save

ARMS = "ABCD"
SEEDS = (71, 113)
STEPS = 720


def baseline_path(artifact_root):
    return Path(
        os.environ.get(
            "COMPAT_INITIAL", Path(artifact_root) / "token-embedding/current-71.pt"
        )
    )


def policy(a, arm):
    net = CellKV(a, "C", arm in "BD")
    baseline = baseline_path(os.environ["ARTIFACT_ROOT"])
    net.load_state_dict(torch.load(baseline, weights_only=True, map_location="cpu"))
    net.requires_grad_(False)
    emb = [
        net.actor.static,
        net.actor.msg,
        net.actor.update,
        net.graph.step,
        net.graph.edge,
        net.graph.message,
        net.actor.dynamic,
        net.actor.age,
    ]
    # Projection to K/V is part of the stored embedding. Freeze it in C.
    emb += [net.actor.input_content, net.actor.latent]
    reader = [
        net.actor.query,
        net.actor.input_role,
        net.actor.lanes,
        net.actor.next_read,
    ]
    for layer in (emb if arm in "BD" else []) + (reader if arm in "CD" else []):
        layer.requires_grad_(True)
    return net


def checkpoint(a, arm, seed):
    return a.out / f"{arm}-{seed}.pt"


def align(left, right, w):
    s, ts = left
    u, us = right
    assert {k: v for k, v in s.items() if k != "ports"} == {
        k: v for k, v in u.items() if k != "ports"
    }
    a = {p[0]: p for p in s["ports"]}
    b = {p[0]: p for p in u["ports"]}
    assert a.keys() == b.keys()
    diff = [ref for ref in a if a[ref] != b[ref]]
    assert len(diff) == 1, (diff, s, u)
    ref = diff[0]
    p, q = a[ref], b[ref]
    assert p[:4] == q[:4] and p[5:] == q[5:] and p[3] == w.tabs.index("Seed")
    assert p[4][0] == q[4][0] and p[4][1] != q[4][1]
    assert p[4][2:] == q[4][2:]
    tids = [
        next(t for t, r in targets if r == (ref,) and t >= w.primitives)
        for targets in (ts, us)
    ]
    assert tids == [w.primitives, w.primitives + 1]
    return ref, tids


def prepare(a):
    actor = load_actor(a.actor, True)
    corpus = {}
    for name, spec in cases("fit"):
        pair = []
        for flip in (False, True):
            w = world(a, actor, name, spec, flip)
            rows = native(a, w, teacher="higher") + native(a, w, teacher="primitive")
            corpus[w.dir.name] = rows
            pair.append(rows[0])
        align(*pair, w)
    torch.save(corpus, a.out / "training.pt")


def train(a):
    rows = torch.load(a.out / "training.pt", weights_only=False)
    actor = load_actor(a.actor, True)
    worlds = {
        w.dir.name: w
        for name, spec in cases("fit")
        for flip in (False, True)
        for w in [world(a, actor, name, spec, flip)]
    }
    for seed in SEEDS:
        for arm in ARMS:
            net = policy(a, arm).train()
            fixed = fixed_digest(net)
            rng = np.random.default_rng(seed)
            path = checkpoint(a, arm, seed)
            losses = []
            counts = Counter()
            if arm != "A":
                opt = torch.optim.AdamW(
                    (p for p in net.parameters() if p.requires_grad),
                    lr=0.0015,
                    weight_decay=0,
                )
                for step in range(STEPS):
                    level = min(2, step // (STEPS // 4))
                    pairs = [
                        (n, sp)
                        for n, sp in cases("fit")
                        if int(n.split("-")[1]) % 3 <= level
                    ]
                    name, _ = pairs[int(rng.integers(len(pairs)))]
                    terms = []
                    for flip in (False, True):
                        n = f"{name}-{int(flip)}"
                        w = worlds[n]
                        net.prepare(w)
                        entries = rows[n]
                        # Replay-supervised whole Tokens, including dynamic continuation
                        # and legal Primitive alternatives. Pair the target entry across flips.
                        s, ts = entries[0]
                        other = rows[f"{name}-{int(not flip)}"][0]
                        ref, tids = (
                            align(other, (s, ts), w)
                            if flip
                            else align((s, ts), other, w)
                        )
                        m = net.state(w, s)
                        terms.append(net.token_loss(w, m, (tids[int(flip)], (ref,))))
                        for _ in range(2):
                            ix = int(rng.integers(len(entries)))
                            s, ts = entries[ix]
                            terms.append(
                                net.token_loss(
                                    w, net.state(w, s), ts[int(rng.integers(len(ts)))]
                                )
                            )
                            counts[
                                "later" if s["run"] != entries[0][0]["run"] else "entry"
                            ] += 1
                    loss = torch.stack(terms).mean()
                    opt.zero_grad(set_to_none=True)
                    loss.backward()
                    torch.nn.utils.clip_grad_norm_(net.parameters(), 3.0)
                    opt.step()
                    losses.append(float(loss.detach()))
            assert fixed_digest(net) == fixed
            torch.save(net.state_dict(), path)
            save(
                path.with_suffix(".json"),
                {
                    "arm": arm,
                    "seed": seed,
                    "updates": len(losses),
                    "complete_targets": 6 * len(losses),
                    "trainable": sum(
                        p.numel() for p in net.parameters() if p.requires_grad
                    ),
                    "frozen_sha": fixed,
                    "additional_targets": dict(counts),
                    "ce90": [float(np.mean(x)) for x in np.array_split(losses, 8)]
                    if losses
                    else [],
                },
            )
            print(arm, seed, len(losses), flush=True)


if __name__ == "__main__":
    torch.set_num_threads(1)
    a = args()
    {"prepare": prepare, "train": train}[a.task](a)
