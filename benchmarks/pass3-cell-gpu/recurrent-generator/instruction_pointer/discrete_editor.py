"""Token editor, mask endpoint model, and an ordered finite-edit CTMC bridge."""

import math

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

from discrete_draft import change
from latent_cell_flow import WIDTH, ZERO


class Rates(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(WIDTH * 5 + 6, 64), nn.SiLU(), nn.Linear(64, 3))

    def forward(self, x):
        return self.net(x)


def features(state, event, vectors, t):
    n = len(vectors)
    out = []
    for i in range(n + 1):
        cur = vectors[i] if i < n else ZERO
        left = vectors[i - 1] if i else ZERO
        right = vectors[i + 1] if i + 1 < n else ZERO
        out.append(
            torch.cat(
                (
                    state,
                    event,
                    cur,
                    (cur - left).abs(),
                    (cur - right).abs(),
                    torch.tensor(
                        [t, float(i < n), float(i > 0), float(i + 1 < n), math.log1p(n), i / max(n, 1)]
                    ),
                )
            )
        )
    return torch.stack(out)


def sampler(net, marks, m, source, method, steps, rng, stats):
    page = getattr(marks, "resident_page", None)
    if page is not None and method == "flow":
        return page.sample(m, source, steps, rng, stats)
    items = source
    next_uid = max((v.uid for v in items), default=-1) + 1

    def rates(t):
        x = features(m.state, m.event, [m.embed(e.cell) for e in items], t)
        stats["edit_forward_calls"] += 1
        stats["sites_scored"] += len(x)
        return net(x).detach()

    def mark(i, sub):
        return marks.draw(m, rng, stats, hint=items[i].cell if sub else None, prefix=items[:i])

    def apply(ops):
        nonlocal items, next_uid
        # Positions refer to the pre-leap draft. Old local IDs never shift.
        for i, k, v in sorted(ops, key=lambda o: (o[0], o[1] != 0), reverse=True):
            new = change(items, i, k, v, m.compatible, next_uid)
            if k == 0:
                next_uid += 1
            if new == items and k == 1:
                stats["blocked_dependent_delete"] += 1
            items = new

    if method == "mask":
        # Predict a window length, including unbounded Poisson insertion multiplicities.
        initial = rates(0)
        positions = []
        for i, row in enumerate(initial):
            n = rng.poisson(F.softplus(row[0]).item())
            positions.extend([(i, True)] * n)
            if i < len(items):
                positions.append((i, False))
        frozen = items
        revealed = {}
        for s in range(steps):
            # Unresolved slots remain masks. Revealed token embeddings condition later reveals.
            vectors = [m.embed(revealed[j]) if j in revealed else ZERO for j in range(len(positions))]
            x = features(m.state, m.event, vectors, s / steps)
            for j, (i, insert) in enumerate(positions):
                if not insert:
                    x[j, 2 * WIDTH : 3 * WIDTH] += m.embed(frozen[i].cell)
            logits = net(x).detach()
            stats["edit_forward_calls"] += 1
            stats["sites_scored"] += len(x)
            for j, (i, insert) in enumerate(positions):
                if j in revealed or rng.random() >= 1 / (steps - s):
                    continue
                if insert:
                    revealed[j] = mark(i, False)
                else:
                    kind = rng.choice(3, p=torch.cat((ZERO[:1], logits[j, 1:])).softmax(0).numpy())
                    if kind == 1:
                        revealed[j] = None
                    elif kind == 2:
                        revealed[j] = mark(i, True) or frozen[i].cell
                    else:
                        revealed[j] = frozen[i].cell
        ops = []
        for j, (i, insert) in enumerate(positions):
            value = revealed[j]
            if insert:
                if value is not None:
                    ops.append((i, 0, value))
            elif value != frozen[i].cell:
                ops.append((i, 1 if value is None else 2, value))
        apply(ops)
        return items
    for s in range(steps if method == "flow" else 1):
        raw = rates(s / steps)
        ops = []
        for i, row in enumerate(raw):
            if method == "editor":
                inserts = int(F.softplus(row[0]).round().item())
                kind = torch.cat((ZERO[:1], row[1:])).argmax().item()
            else:
                # Frozen rates tau-leap. u=softplus(logit)/(1-t), dt=1/steps.
                lam = F.softplus(row).numpy() / (steps - s)
                inserts = rng.poisson(lam[0])
                total = float(lam[1:].sum())
                kind = (1 + int(rng.random() * total > lam[1])) if rng.random() < -math.expm1(-total) else 0
            if i < len(items) and kind:
                value = mark(i, True) if kind == 2 else None
                if kind == 1 or value is not None:
                    ops.append((i, kind, value))
            for _ in range(inserts):
                value = mark(i, False)
                if value is not None:
                    ops.append((i, 0, value))
        stats["sampled_edits"] += len(ops)
        apply(ops)
    return items


def supervised(source, target):
    """Aligned endpoint commands at original positions, including all tail insertions."""
    labels = torch.zeros(len(source) + 1, 3)
    common = min(len(source), len(target))
    for i in range(common):
        if source[i].cell != target[i].cell:
            labels[i, 2] = 1
    for i in range(common, len(source)):
        labels[i, 1] = 1
    labels[len(source), 0] = max(0, len(target) - common)
    return labels


def train_positions(records, method, seed):
    rng = np.random.default_rng(seed)
    torch.manual_seed(seed)
    model = Rates()
    opt = torch.optim.AdamW(model.parameters(), lr=0.002)
    for epoch in range(55):
        rows = []
        labels = []
        maskrows = []
        masklabels = []
        for _ in range(192):
            z, e, src, dst, vec, path = records[rng.integers(len(records))]
            if method == "flow":
                count = len(path)
                k = rng.integers(count + 1)
                t = float(rng.beta(k + 1, count - k + 1))
                current = path[k][0] if k < count else dst
                y = torch.zeros(len(current) + 1, 3)
                if k < count:
                    _, i, kind, _ = path[k]
                    y[i, kind] = count - k
                x = features(z, e, [vec[v.cell] for v in current], t)
            else:
                x = features(z, e, [vec[v.cell] for v in src], 0)
                y = supervised(src, dst)
                if method == "mask":
                    t = rng.random()
                    parts = []
                    target = []
                    known = {}
                    for j in range(max(len(src), len(dst))):
                        s = src[j].cell if j < len(src) else None
                        d = dst[j].cell if j < len(dst) else None
                        if rng.random() < t:
                            known[j] = d
                        parts.append(vec[d] if j in known and d is not None else ZERO)
                        target.append(
                            -100 if j in known or s is None else (0 if s == d else 1 if d is None else 2)
                        )
                    mx = features(z, e, parts, t)
                    for j, v in enumerate(src):
                        mx[j, 2 * WIDTH : 3 * WIDTH] += vec[v.cell]
                    maskrows.extend(mx[:-1])
                    masklabels.extend(target)
            rows.append(x)
            labels.append(y)
        x = torch.cat(rows)
        y = torch.cat(labels)
        for ids in torch.randperm(len(x)).split(128):
            p = model(x[ids])
            truth = y[ids]
            if method == "flow":
                mu = F.softplus(p)
                # Time-weighted Poisson Bregman rate matching. Multiplying by (1-t)
                # removes the endpoint singularity and preserves the conditional minimizer.
                allowed = torch.ones_like(p)
                allowed[:, 1:] = x[ids, -5, None]
                loss = ((mu - truth * mu.clamp_min(1e-8).log()) * allowed).sum(1).mean()
            else:
                mu = F.softplus(p[:, 0])
                loss = (mu - truth[:, 0] * mu.clamp_min(1e-8).log()).mean()
                if method == "editor":
                    cls = truth[:, 1] + 2 * truth[:, 2]
                    loss = loss + F.cross_entropy(
                        torch.cat((torch.zeros(len(ids), 1), p[:, 1:]), 1), cls.long()
                    )
            opt.zero_grad()
            loss.backward()
            opt.step()
        if method == "mask" and any(v != -100 for v in masklabels):
            scores = model(torch.stack(maskrows))
            loss = F.cross_entropy(
                torch.cat((torch.zeros(len(scores), 1), scores[:, 1:]), 1), torch.tensor(masklabels)
            )
            opt.zero_grad()
            loss.backward()
            opt.step()
    return model.eval()
