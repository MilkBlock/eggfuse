"""Offline, same-state CCP interventions. No oracle objects are given to a policy."""

import itertools
import json
import os
import random
from collections import defaultdict
from copy import copy

import torch

from cell_kv_runtime import native
from interface_role_world import mixed
from partner_index_worlds import args
from selected_cell_study import model
from selected_cell_study import world as previous_world

KINDS = ("single", "mixed", "arity", "fork", "aliases")


def world(a, actor, k, i, train):
    if k != "aliases":
        return previous_world(a, actor, k, i, train)
    local = copy(a)
    local.out = out(a)
    return mixed(
        local,
        actor,
        (198401 if train else 202911) + i // 2,
        i % 2,
        depth=1 + i // 2 % 2 if train else 3,
        extra_rules=True,
        equivalent=True,
    )


def out(a):
    d = a.out / "competition"
    d.mkdir(exist_ok=True)
    return d


def rowskey(res):
    return frozenset((table, tuple(args)) for table, args in res["facts"])


def candidates(w, s):
    for t in s["menu"]:
        roles = w.roles[w.layouts[t][0][0]]
        banks = [[p[0] for p in s["ports"] if p[3] == tab] for tab in roles]
        for refs in itertools.product(*banks):
            yield t, refs


def audit(a, w, s):
    def replay(actions):
        return native(a, w, teacher="higher", branch=(s, actions))

    base = rowskey(replay([]))
    verified = {}
    unknown = 0
    for t, r in candidates(w, s):
        res = replay([(t, r)])
        new = rowskey(res)
        complete = (
            t < w.primitives or res["stats"].get("branch_higher_completed", 0) == 1
        )
        if base < new and complete:
            verified[t, r] = tuple(sorted(new - base))
        else:
            unknown += 1
    return verified, unknown


def prepare(a, split):
    import pickle

    net = model(a, 71, "direct", True)
    for kind in KINDS if split == "train" else ("arity", "aliases"):
        for i in range(12 if split == "train" else 4):
            path = out(a) / f"{split}-{kind}-{i}.pkl"
            if path.exists():
                continue
            w = world(a, net.actor, kind, i, split == "train")
            data = []
            for s, targets in native(a, w, teacher="higher"):
                verified, unknown = audit(a, w, s)
                data.append((s, targets, verified, unknown))
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(pickle.dumps(data))
            tmp.replace(path)


def train(a, arm, seed):
    import pickle

    net = model(a, seed, "direct", True).train()
    data = {k: [] for k in KINDS}
    for k in KINDS:
        for i in range(12):
            w = world(a, net.actor, k, i, True)
            rs = pickle.loads((out(a) / f"train-{k}-{i}.pkl").read_bytes())
            data[k].append((w, rs))
    # Independent random streams keep state draws identical for A/B.
    sched = random.Random(seed)
    labels = random.Random(71000 + seed)
    opt = torch.optim.AdamW(
        [p for p in net.parameters() if p.requires_grad], lr=0.001, weight_decay=0
    )
    stats = defaultdict(int)
    curve = []
    for step in range(420):
        weights = (
            (22, 16, 11, 11)
            if arm != "C"
            else ((12, 6, 1, 1), (6, 6, 4, 4), (4, 4, 6, 6))[step // 140]
        )
        k = sched.choices(KINDS[:4], weights)[0]
        if k == "arity" and sched.randrange(2):
            k = "aliases"
        w, rs = sched.choice(data[k])
        loss = []
        for s, ts, ver, _ in (rs[0], sched.choice(rs[1:])):
            choices = [t for t in ts if t in ver]
            if not choices or not ver:
                raise ValueError(("no verified trajectory target", k, s["run"]))
            by = defaultdict(list)
            for t, g in ver.items():
                by[g].append(t)
            if arm == "A":
                targets = labels.choices(choices, k=8)
            else:
                targets = [labels.choice(by[g]) for g in labels.choices(list(by), k=8)]
            net.prepare(w)
            m = net.state(w, s)
            nll = {t: net.token_loss(w, m, t) for t in set(targets)}
            loss.extend(nll[t] for t in targets)
            stats[k] += 8
        ce = torch.stack(loss).mean()
        opt.zero_grad(set_to_none=True)
        ce.backward()
        torch.nn.utils.clip_grad_norm_(net.parameters(), 3)
        opt.step()
        if step % 30 == 0 or step == 419:
            curve.append((step + 1, float(ce.detach()), dict(stats)))
    torch.save(net.state_dict(), out(a) / f"{arm}-{seed}.pt")
    (out(a) / f"{arm}-{seed}-curve.json").write_text(json.dumps(curve))


if __name__ == "__main__":
    torch.set_num_threads(1)
    a = args()
    if a.task == "train":
        train(a, os.environ["COMP_ARM"], int(os.environ["COMP_SEED"]))
    else:
        prepare(a, os.environ["COMP_SPLIT"])
