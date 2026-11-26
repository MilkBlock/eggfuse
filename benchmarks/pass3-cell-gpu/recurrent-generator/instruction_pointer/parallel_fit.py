"""Train an endpoint set editor and the conditional jump rates of a uniform reveal path."""

import json
from collections import Counter

import numpy as np
import torch
from torch.nn.functional import cross_entropy

from discrete_draft import Cell, plan
from draft_multitarget import snapshots
from latent_cell_flow import ZERO
from metal_scaling import models
from parallel_budget import args
from parallel_memory import make_memory

CAPS = (4, 16, 64, 256)
TRAIN = (
    ("sum", "teacher"),
    ("dot", "teacher"),
    ("grammar-benefit-fork-17118", "teacher"),
    ("sum", "stream"),
    ("grammar-benefit-fork-17118", "stream"),
)


def site_features(state, event, vectors, live, t):
    # Occupied slots can be anywhere during training. Online they are packed.
    cap = len(vectors)
    mask = live[:, None]
    n = live.sum()
    pool = (vectors * mask).sum(0) / n.clamp_min(1)
    scalar = torch.stack(
        (
            torch.full_like(live, t),
            live,
            torch.full_like(live, 1 / cap),
            n.expand(cap) / cap,
            torch.log1p(n).expand(cap),
            torch.full_like(live, np.log1p(cap)),
        ),
        1,
    )
    return torch.cat(
        (
            state.expand(cap, -1),
            event.expand(cap, -1),
            vectors,
            pool.expand(cap, -1),
            (vectors - pool).abs(),
            scalar,
        ),
        1,
    ), pool


def align(source, target, rng):
    """Match common complete marks first. Vacant slots are interchangeable."""
    remaining = set(target)
    end = [None] * len(source)
    free = []
    for i in rng.permutation(len(source)):
        if source[i] is not None and source[i] in remaining:
            end[i] = source[i]
            remaining.remove(source[i])
        else:
            free.append(i)
    for i, c in zip(free, [c for c in target if c in remaining]):
        end[i] = c
    return end


def coupled(source, target, t, rng):
    end = align(source, target, rng)
    return [
        y if u < t else x
        for u, x, y in zip(rng.random(len(end)), source, end, strict=True)
    ], end


@torch.no_grad()
def collect(a):
    net, _ = models("1M")
    rng = np.random.default_rng(3127)
    actions = []
    addresses = []
    counts = Counter()
    for case, src in TRAIN:
        for m, run, g in snapshots(a, case, src, make_memory):
            gold = list(g)
            state = m.state.clone()
            event = m.event.clone()
            gold_vec = {c: m.embed(c) for c in gold}
            counts["states"] += 1
            for j in range(12):
                cap = CAPS[j % 4]
                cut = 0 if j < 4 else int(rng.integers(len(gold) + 1))
                rest = gold[cut:]
                m.state = state
                prior = gold[max(0, cut - cap) : cut]
                attempted = (
                    torch.stack([gold_vec[c] for c in prior]).mean(0) if prior else ZERO
                )
                m.event = (event + 0.5 * attempted).tanh()
                if cut:
                    m.reply([(gold[cut - 1], True)])
                goal = [rest[i] for i in rng.permutation(len(rest))[:cap]]
                source = [None] * cap
                if goal and j % 3:
                    for i in rng.choice(cap, int(rng.integers(cap + 1)), replace=False):
                        c = goal[int(rng.integers(len(goal)))]
                        if j % 3 == 2 and c.refs and rng.random() < 0.5:
                            # Unverified corrupt binding is a draft distractor only.
                            c = Cell(c.rule, tuple((*r[:2], r[2] + 1) for r in c.refs))
                        source[i] = c
                t = 0.0 if j < 4 else float(rng.uniform(0, 1))
                cur, end = coupled(source, goal, t, rng)
                emb = {c: m.embed(c) for c in set(cur) if c is not None}
                vec = torch.stack([emb.get(c, ZERO) for c in cur])
                live = torch.tensor([float(c is not None) for c in cur])
                x, pool = site_features(m.state, m.event, vec, live, t)
                y = torch.tensor(
                    [
                        0 if c == v else 1 if v is None else 2
                        for c, v in zip(cur, end, strict=True)
                    ]
                )
                actions.append((x, y, torch.full((cap,), 1 / (1 - t))))
                m.draft_pool = pool
                prefix = plan([c for c in cur if c is not None])
                for i, (c, v) in enumerate(zip(cur, end, strict=True)):
                    if y[i] != 2:
                        continue
                    before = (
                        prefix
                        if c is None
                        else prefix[: sum(q is not None for q in cur[:i])]
                    )
                    trace = []
                    got = net.draw(
                        m, None, counts, hint=c, target=v, records=trace, prefix=before
                    )
                    if got != v:
                        raise ValueError("verified endpoint lost its named address")
                    addresses.extend((k, bit, 1 / (1 - t)) for k, bit, _ in trace)
                m.draft_pool = None
                counts["pages"] += 1
                counts["goal_tokens"] += len(goal)
            m.state = state
            m.event = event
    return actions, addresses, counts


def fit(a):
    actions, addresses, counts = collect(a)
    x, y, w = map(torch.cat, zip(*actions))
    z, b, v = zip(*addresses)
    z = torch.stack(z)
    b = torch.tensor(b).float()
    v = torch.tensor(v)
    initial = torch.load(a.previous / "s243/1M-n1000000/weights.pt", weights_only=True)
    log = {}
    for method in ("editor", "flow"):
        marks, rates = models("1M")
        for net, sd in zip((marks, rates), initial, strict=True):
            net.load_state_dict(sd)
        opt = torch.optim.AdamW([*marks.parameters(), *rates.parameters()], lr=0.00025)
        gen = torch.Generator().manual_seed(182)
        losses = []
        for _ in range(a.updates):
            ia = torch.randint(len(x), (512,), generator=gen)
            ib = torch.randint(len(z), (512,), generator=gen)
            labels = y[ia]
            logits = rates(x[ia])
            logits[:, 1] = logits[:, 1].masked_fill(x[ia, 161] == 0, -1e4)
            lp = logits.log_softmax(1)
            # Keep is an implicit self-loop. Off-diagonal rates are p(edit)/(1-t).
            if method == "flow":
                risk = (
                    1
                    - lp[:, 0].exp()
                    - (labels != 0) * lp.gather(1, labels[:, None]).squeeze(1)
                )
                loss = (risk * w[ia]).mean()
            else:
                loss = cross_entropy(logits, labels)
            markloss = torch.nn.functional.binary_cross_entropy_with_logits(
                marks.choice(z[ib]).flatten(), b[ib], reduction="none"
            )
            loss = loss + (markloss * (v[ib] if method == "flow" else 1)).mean()
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(
                [*marks.parameters(), *rates.parameters()], 5.0
            )
            opt.step()
            losses.append(float(loss.detach()))
        torch.save([marks.state_dict(), rates.state_dict()], a.out / (method + ".pt"))
        log[method] = [float(np.mean(chunk)) for chunk in np.array_split(losses, 4)]
        print(method, log[method], flush=True)
    (a.out / "fit.json").write_text(
        json.dumps(
            {
                "counts": counts,
                "sites": len(x),
                "decisions": len(z),
                "loss": log,
                "updates": a.updates,
            }
        )
        + "\n"
    )


if __name__ == "__main__":
    p = args()
    p.add_argument("--updates", type=int, default=640)
    torch.set_num_threads(1)
    fit(p.parse_args())
