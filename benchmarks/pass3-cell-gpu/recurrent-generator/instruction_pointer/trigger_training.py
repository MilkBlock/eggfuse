"""Matched positive full-Token CE with rule-local publication observations."""

import hashlib
import json
import os
import pickle
import random
from time import perf_counter

import torch

from cell_kv_runtime import native
from foundation_fit import model
from foundation_wake import world as wake_world
from foundation_world import folder, world
from partner_index_worlds import args

MODES = ("none", "dirty", "both")


def directory(a):
    path = a.out / "rule-publication"
    path.mkdir(exist_ok=True)
    return path


def corpus(a, actor):
    sets = [[], []]
    pairs = []
    for train, count in ((True, 12), (False, 6)):
        for i in range(count):
            for distinct, tag in ((False, "wake"), (True, "wake-asym")):
                w = wake_world(a, actor, i, train, distinct)
                obs = pickle.loads((folder(a) / f"{tag}-{train}-{i}.pkl").read_bytes())
                for o in obs:
                    for phase in (0, 2, 3):
                        s, flags, items = o["states"][phase]
                        snap = dict(s, rule_state=flags)
                        if train:
                            sets[0].append(
                                (w, snap, [t for t, _, valid in items if valid])
                            )
                        elif phase:
                            pairs.append(
                                (
                                    tag,
                                    i,
                                    o["first"],
                                    o["consumed"],
                                    phase,
                                    w,
                                    snap,
                                    o["target"],
                                )
                            )
            if train:
                w = world(a, actor, i, True, "multi")
                replay = {
                    s["run"]: s
                    for s, _ in native(
                        a, w, teacher="primitive", rule_state=True, receipt_memory=True
                    )
                }
                for old, ts in pickle.loads(
                    (folder(a) / f"states-multi-1-{i}.pkl").read_bytes()
                ):
                    s = replay[old["run"]]
                    assert {
                        k: v
                        for k, v in s.items()
                        if k not in ("rule_state", "check_dirty")
                    } == old
                    sets[1].append((w, s, ts))
    return sets, pairs


def train(a, seed, mode, sets):
    n = model(a, seed, 32)
    n.rule_condition = mode
    rng = random.Random(seed + 978)
    opt = torch.optim.AdamW(
        [p for p in n.parameters() if p.requires_grad], lr=0.001, weight_decay=0.0
    )
    h = hashlib.sha256()
    start = perf_counter()
    for step in range(512):
        n.train()
        terms = []
        for _ in range(4):
            group = int(rng.random() < 0.25)
            ix = rng.randrange(len(sets[group]))
            w, s, ts = sets[group][ix]
            n.prepare(w)
            m = n.state(w, s)
            target_ids = rng.choices(range(len(ts)), k=4)
            h.update(str((group, ix, target_ids)).encode())
            losses = {j: n.token_loss(w, m, ts[j]) for j in set(target_ids)}
            terms.extend(losses[j] for j in target_ids)
        opt.zero_grad(set_to_none=True)
        torch.stack(terms).mean().backward()
        torch.nn.utils.clip_grad_norm_(n.parameters(), 3)
        opt.step()
    out = directory(a)
    (out / f"train-{mode}-{seed}.json").write_text(
        json.dumps(
            {
                "stream": h.hexdigest(),
                "examples": 8192,
                "steps": 512,
                "params": sum(p.numel() for p in n.parameters() if p.requires_grad),
                "seconds": perf_counter() - start,
            }
        )
    )
    torch.save(n.state_dict(), out / f"{mode}-{seed}.pt")
    return n


def probes(n, pairs, mode):
    rows = []
    n.eval()
    n.physical = ("held", 0)
    with torch.no_grad():
        for tag, i, first, consumed, phase, w, s, t in pairs:
            n.prepare(w)
            flags = s["rule_state"]
            roots = list(flags)
            assert len(roots) == 2
            for intervention in (
                "real",
                "swap",
                "swap_dirty",
                "swap_wm",
                "mute_dirty",
                "mute_wm",
            ):
                changed = {}
                for rid, other in zip(roots, reversed(roots), strict=True):
                    wm, d = flags[rid]
                    ow, od = flags[other]
                    changed[rid] = (
                        0
                        if intervention == "mute_wm"
                        else ow
                        if intervention in ("swap", "swap_wm")
                        else wm,
                        False
                        if intervention == "mute_dirty"
                        else od
                        if intervention in ("swap", "swap_dirty")
                        else d,
                    )
                m = n.state(w, dict(s, rule_state=changed))
                rows.append(
                    {
                        "tag": tag,
                        "i": i,
                        "first": first,
                        "consumed": consumed,
                        "phase": phase,
                        "intervention": intervention,
                        "p": float((-n.token_loss(w, m, t)).exp()),
                        "template": float(
                            m["root_lp"][list(m["families"]).index(t[0])].exp()
                        ),
                    }
                )
    return rows


if __name__ == "__main__":
    a = args()
    torch.set_num_threads(1)
    seed = int(os.getenv("TR_SEED", "71"))
    sets, pairs = corpus(a, model(a, seed, 32).actor)
    for mode in MODES:
        n = train(a, seed, mode, sets)
        print(seed, mode, "trained", flush=True)
        (directory(a) / f"pairs-{mode}-{seed}.json").write_text(
            json.dumps(probes(n, pairs, mode))
        )
