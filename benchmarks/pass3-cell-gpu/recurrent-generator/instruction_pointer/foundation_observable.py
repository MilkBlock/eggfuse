"""Offline positive control: unmasked raw native state in the existing Recipe code lanes."""

import json
import pickle
import random

import torch

from foundation_fit import model
from foundation_wake import world
from foundation_world import folder
from partner_index_worlds import args
from query_environment import stamp


def condition(n, w, s, flags, mode):
    n.prepare(w)
    nodes, codes, types = n.cache
    raw = codes.new_zeros(codes.shape)
    for t in s["menu"]:
        rid = w.layouts[t][0][0]
        wm, dirty = flags[rid]
        if mode in ("both", "dirty"):
            raw[t, 0] = float(dirty)
        if mode in ("both", "wm"):
            raw[t, 1] = stamp(wm)
    n.cache = (nodes, codes + raw, types)
    try:
        return n.state(w, s)
    finally:
        n.cache = (nodes, codes, types)


def run(a, distinct, seed):
    tag = "wake-asym" if distinct else "wake"
    out = folder(a)
    n = model(a, seed, 32)

    def load(train, count):
        return [
            (
                world(a, n.actor, i, train, distinct),
                pickle.loads((out / f"{tag}-{train}-{i}.pkl").read_bytes()),
            )
            for i in range(count)
        ]

    train = load(True, 12)
    evals = load(False, 6)
    opt = torch.optim.AdamW(
        [p for p in n.parameters() if p.requires_grad], lr=0.001, weight_decay=0
    )
    rng = random.Random(seed + 311)
    rows = []
    for step in range(513):
        if step in (0, 32, 128, 512):
            n.eval()
            n.physical = ("held", 0)
            with torch.no_grad():
                for i, (w, obs) in enumerate(evals):
                    for o in obs:
                        for phase in (2, 3):
                            s, flags, items = o["states"][phase]
                            t = o["target"]
                            for mode in (
                                ("both", "wm", "dirty", "none")
                                if step == 512
                                else ("both",)
                            ):
                                m = condition(n, w, s, flags, mode)
                                idx = list(m["families"]).index(t[0])
                                rows.append(
                                    {
                                        "step": step,
                                        "i": i,
                                        "branch": o["first"],
                                        "consumed": o["consumed"],
                                        "phase": phase,
                                        "mode": mode,
                                        "p": float((-n.token_loss(w, m, t)).exp()),
                                        "template": float(m["root_lp"][idx].exp()),
                                    }
                                )
        if step == 512:
            break
        n.train()
        terms = []
        for _ in range(4):
            w, obs = rng.choice(train)
            ph = rng.choice((0, 2, 3))
            s, flags, items = rng.choice(obs)["states"][ph]
            targets = rng.choices([t for t, _, g in items if g], k=4)
            m = condition(n, w, s, flags, "both")
            losses = {t: n.token_loss(w, m, t) for t in set(targets)}
            terms.extend(losses[t] for t in targets)
        opt.zero_grad(set_to_none=True)
        torch.stack(terms).mean().backward()
        torch.nn.utils.clip_grad_norm_(n.parameters(), 3)
        opt.step()
    (out / f"probe-{tag}-{seed}.json").write_text(
        json.dumps(rows, separators=(",", ":"))
    )
    torch.save(n.state_dict(), out / f"probe-{tag}-{seed}.pt")


if __name__ == "__main__":
    torch.set_num_threads(1)
    for distinct in (False, True):
        for seed in (71, 113):
            run(args(), distinct, seed)
