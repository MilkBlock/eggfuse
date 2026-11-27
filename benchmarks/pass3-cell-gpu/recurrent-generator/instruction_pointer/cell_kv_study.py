"""Full-token CE on mixed native Primitive/Higher trajectories and autonomous evaluation."""

import hashlib
import json
import os
from collections import defaultdict

import numpy as np
import torch

from cell_kv_model import CellKV
from cell_kv_runtime import native
from cell_kv_world import World, make
from first_parent import records
from partner_index_worlds import args
from rule_read import load_actor


def names(split):
    if split == "train":
        return [
            (
                f"fit-{depth}-{jobs}-{parity}",
                depth,
                jobs,
                36000 + 1000 * depth + 100 * jobs + parity,
            )
            for depth in (1, 2, 3)
            for jobs in (1, 2, 4)
            for parity in (0, 1)
        ]
    return [
        (f"blind-{i}", 4 + 2 * (i % 2), 2 + i % 3, 971591 + i * 53, i >= 2)
        for i in range(4)
    ]


def groups(net):
    return dict(
        recipe_gnn=[net.actor.msg, net.actor.update, net.actor.static],
        layout_gnn=[net.graph.step, net.graph.edge, net.graph.message],
        memory_key=[net.actor.input_content],
        query=[net.actor.query],
        value=[net.actor.latent],
        dynamic=[net.actor.dynamic],
        reference_update=[net.actor.next_read],
        template_projection=[net.actor.input_role],
    )


def params(modules):
    return [p for module in modules for p in module.parameters()]


def vector(modules, grad=False):
    return torch.cat(
        [
            (
                p.detach()
                if not grad
                else p.grad.detach()
                if p.grad is not None
                else torch.zeros_like(p)
            ).flatten()
            for p in params(modules)
        ]
    )


def corpus(a):
    actor = load_actor(a.actor, True)
    states = {}
    for name, depth, jobs, seed in names("train"):
        w = World(make(a, name, depth, jobs, seed), actor)
        states[name] = native(a, w, teacher="primitive") + native(
            a, w, teacher="higher"
        )
    torch.save(states, a.out / "training.pt")
    print("verified states", sum(map(len, states.values())), flush=True)


def checkpoint(a, arm, graph, seed, step):
    return (
        a.out / "weights" / f"{arm}-{'joint' if graph else 'frozen'}-{seed}-{step}.pt"
    )


def train(a):
    states = torch.load(a.out / "training.pt", weights_only=False)
    (a.out / "weights").mkdir(exist_ok=True)
    steps = int(os.environ.get("STEPS", "360"))
    for arm in os.environ.get("KV_ARMS", "ABCD"):
        for joint in (False, True):
            for seed in map(int, os.environ.get("KV_SEEDS", "71,113").split(",")):
                path = checkpoint(a, arm, joint, seed, steps)
                if path.exists():
                    continue
                torch.manual_seed(seed)
                net = CellKV(a, arm, joint).train()
                worlds = {
                    name: World(a.out / "worlds" / name, net.actor) for name in states
                }
                rng = np.random.default_rng(seed)
                layers = groups(net)
                before = {k: vector(v) for k, v in layers.items()}
                grad = defaultdict(float)
                metrics = []
                opt = torch.optim.AdamW(
                    [p for p in net.parameters() if p.requires_grad],
                    lr=0.0015,
                    weight_decay=0.0,
                )
                losses = []
                for step in range(steps):
                    # Equal exposures across arms. Retain small instances throughout.
                    eligible = [
                        name
                        for name, depth, jobs, _ in names("train")
                        if jobs <= (2 if step < steps // 3 else 4)
                    ]
                    name = rng.choice(eligible)
                    w = worlds[name]
                    net.prepare(w)
                    terms = []
                    for i in rng.choice(len(states[name]), 3, replace=True):
                        s, targets = states[name][i]
                        m = net.state(w, s)
                        for j in rng.choice(len(targets), 2, replace=True):
                            terms.append(net.token_loss(w, m, targets[j]))
                    loss = torch.stack(terms).mean()
                    opt.zero_grad()
                    loss.backward()
                    for k, v in layers.items():
                        grad[k] += (
                            sum(
                                float(p.grad.detach().square().sum())
                                for p in params(v)
                                if p.grad is not None
                            )
                            ** 0.5
                        )
                    torch.nn.utils.clip_grad_norm_(net.parameters(), 3.0)
                    opt.step()
                    losses.append(loss.item())
                    if step + 1 in (1, steps // 3, steps * 2 // 3, steps):
                        for k, v in layers.items():
                            metrics.append(
                                dict(
                                    arm=arm,
                                    joint=int(joint),
                                    seed=seed,
                                    updates=step + 1,
                                    complete_tokens=(step + 1) * 6,
                                    group=k,
                                    mean_grad_norm=grad[k] / (step + 1),
                                    parameter_delta_norm=float(
                                        (vector(v) - before[k]).norm()
                                    ),
                                    mean_ce=np.mean(losses[-min(60, len(losses)) :]),
                                )
                            )
                records(path.with_suffix(".csv"), metrics)
                torch.save(net.state_dict(), path)
                print(path.name, metrics[-1]["mean_ce"], flush=True)


def digest(w):
    return [
        hashlib.sha256(repr(w.cat.int_bake.key(layout)).encode()).hexdigest()
        for layout in w.layouts[w.primitives :]
    ]


@torch.no_grad()
def evaluate(a):
    steps = int(os.environ.get("STEPS", "360"))
    # New evaluation programs and layouts are compiled only after training finishes.
    for arm in os.environ.get("KV_ARMS", "ABCD"):
        for joint in (False, True):
            for seed in map(int, os.environ.get("KV_SEEDS", "71,113").split(",")):
                if not checkpoint(a, arm, joint, seed, steps).exists():
                    raise FileNotFoundError("finish training before post-freeze Bake")
    actor = load_actor(a.actor, True)
    train_sigs = {
        sig
        for name, *_ in names("train")
        for sig in digest(World(a.out / "worlds" / name, actor))
    }
    hold = [World(make(a, *spec), actor) for spec in names("held")]
    assert all(not set(digest(w)) & train_sigs for w in hold)
    results = []
    for seed in map(int, os.environ.get("KV_SEEDS", "71,113").split(",")):
        for w in hold:
            for draw in (193, 827):
                configs = [
                    (arm, joint, step)
                    for arm in os.environ.get("KV_ARMS", "ABCD")
                    for joint in (False, True)
                    for step in (0, steps)
                    if step or not joint
                ]
                for block in (0, 1):
                    for arm, joint, step in (
                        configs
                        if (block + (draw == 827)) % 2 == 0
                        else reversed(configs)
                    ):
                        net = CellKV(a, arm, joint).eval()
                        if step:
                            net.load_state_dict(
                                torch.load(
                                    checkpoint(a, arm, joint, seed, step),
                                    weights_only=True,
                                )
                            )
                        r = native(a, w, policy=net, seed=draw)
                        results.append(
                            dict(
                                case=w.dir.name,
                                block=block,
                                arm=arm,
                                joint=joint,
                                updates=step,
                                seed=seed,
                                draw=draw,
                                **r,
                            )
                        )
            (a.out / os.environ.get("KV_NATIVE_FILE", "native.json")).write_text(
                json.dumps(results, separators=(",", ":")) + "\n"
            )
            print("native", seed, w.dir.name, len(results), flush=True)


if __name__ == "__main__":
    torch.set_num_threads(1)
    a = args()
    {"prepare": corpus, "train": train, "live": evaluate}[a.task](a)
