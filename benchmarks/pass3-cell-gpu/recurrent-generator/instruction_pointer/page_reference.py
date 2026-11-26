"""Scalar reference for the device page's independent per-site and per-proposal random streams."""

import math

from torch.nn import functional as F

from discrete_draft import change
from discrete_editor import features


def mix(x):
    x &= 0xFFFFFFFF
    x = ((x ^ (x >> 16)) * 0x7FEB352D) & 0xFFFFFFFF
    x = ((x ^ (x >> 15)) * 0x846CA68B) & 0xFFFFFFFF
    return x ^ (x >> 16)


class Random:
    def __init__(self, page, domain, index):
        self.state = mix(mix(page ^ domain) + index)

    def random(self):
        self.state = (self.state + 0x9E3779B9) & 0xFFFFFFFF
        return ((mix(self.state) >> 9) + 0.5) / 8388608

    def poisson(self, mean):
        total = 0
        while mean > 0:
            part = min(mean, 12)
            cutoff = math.exp(-part)
            prod = self.random()
            while prod > cutoff:
                total += 1
                prod *= self.random()
            mean -= part
        return total


class ScalarPage:
    def __init__(self, marks, rates, counts):
        self.marks, self.rates, self.counts = marks, rates, counts

    def sample(self, m, source, steps, rng, stats):
        seed = int(rng.integers(1, 2**31))
        items = source
        next_uid = max((it.uid for it in source), default=-1) + 1
        for s in range(steps):
            x = features(
                m.state, m.event, [m.embed(it.cell) for it in items], s / steps
            )
            rates = F.softplus(self.rates(x)).detach().cpu().numpy() / (steps - s)
            jobs = []
            for i, row in enumerate(rates):
                random = Random(seed, s + 1, 2 * i)
                inserts = random.poisson(float(row[0]))
                total = float(row[1:].sum())
                if i < len(items) and random.random() < -math.expm1(-total):
                    jobs.append((i, 2 if random.random() * total > row[1] else 1))
                jobs.extend([(i, 0)] * inserts)
            ops = []
            for g, (i, kind) in enumerate(jobs):
                mark = None
                if kind != 1:
                    mark = self.marks.draw(
                        m,
                        Random(seed, 33 + s, 2 * g + 1),
                        stats,
                        hint=items[i].cell if kind == 2 else None,
                        prefix=items[:i],
                    )
                    if mark is None:
                        continue
                ops.append((i, kind, mark))
            for i, k, v in sorted(ops, key=lambda a: (a[0], a[1] != 0), reverse=True):
                items = change(items, i, k, v, m.compatible, next_uid)
                next_uid += int(k == 0)
            stats["sampled_edits"] += len(ops)
            stats["edit_forward_calls"] += 1
            stats["sites_scored"] += len(x)
        return items
