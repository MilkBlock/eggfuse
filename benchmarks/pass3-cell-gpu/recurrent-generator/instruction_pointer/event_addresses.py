"""Cell-triggered subscriptions and neural address ranges on ordered LSH postings."""

from collections import defaultdict
import math
import numpy as np
import torch
from torch import nn

WIDTH = 41
PAGE = 256


class AddressNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.body = nn.Sequential(
            nn.Linear(WIDTH, 64), nn.Tanh(), nn.Linear(64, 48), nn.Tanh()
        )
        self.action = nn.Linear(48, 3)

    def forward(self, x):
        return self.action(self.body(x))


class Bank:
    def __init__(self, rd, table):
        # Preserve native publication order under arbitrary renaming of Cell IDs.
        self.ports = list(rd.live[table])
        self.positions = {a: i for i, a in enumerate(self.ports)}
        self.fields = {}
        self.rows = np.array(
            [(*a, rd.store.visible[a]["version"]) for a in self.ports], dtype=np.int64
        ).reshape(-1, 3)
        self.version_order = self.rows[:, 2].argsort(kind="stable")
        self.versions = self.rows[self.version_order, 2]
        self.vec = np.empty((len(self.ports), 16), np.float32)
        self.codes = []
        for i, a in enumerate(self.ports):
            h = rd.index.keys[a]
            self.vec[i, :12] = h.mean(0)[:12].numpy() if len(h) else 0
            kind = rd.store.types[a[0]][0]
            self.vec[i, 12:] = [
                float(kind == "generated"),
                float(kind == "repair"),
                math.sin(a[1]),
                math.cos(a[1]),
            ]
            self.codes.append(rd.index.rows[a][2])
        self.codes = np.array(self.codes, dtype=np.int64)

    def postings(self, col):
        if col not in self.fields:
            code = self.codes[:, col]
            order = code.argsort(kind="stable")
            self.fields[col] = (
                order,
                np.r_[0, np.bincount(code, minlength=256).cumsum()],
            )
        return self.fields[col]


class Directory:
    def __init__(self, rd, stats):
        self.rd, self.stats = rd, stats
        self.cache = {}
        self.orders = {}
        self.roles = {}
        self.subs = defaultdict(list)
        for r, roles in enumerate(rd.iface.roles):
            tabs = tuple(rd.tabs[t] for t, _ in roles)
            self.roles[r] = tabs
            for slot, t in enumerate(tabs):
                self.subs[t].append((r, slot))

    def bank(self, t):
        v = self.rd.versions[t]
        if t not in self.cache or self.cache[t][0] != v:
            self.cache[t] = v, Bank(self.rd, t)
            self.stats["index_port_reads"] += len(self.cache[t][1].ports)
        return self.cache[t][1]

    def events(self, rules):
        # Table subscriptions meet just the currently scheduled rule watermarks.
        for t, subs in self.subs.items():
            eligible = [(r, j, rules[r]) for r, j in subs if r in rules]
            if not eligible:
                continue
            b = self.bank(t)
            for r, j, wm in eligible:
                ix = b.version_order[np.searchsorted(b.versions, wm) :]
                if len(ix):
                    yield r, j, ix
        for r in rules:
            if not self.roles[r]:
                yield r, -1, np.array([0])

    def order(self, r, start):
        if start < 0:
            return ()
        if (r, start) in self.orders:
            return self.orders[r, start]
        roles = self.roles[r]
        chosen = [start]
        while len(chosen) < len(roles):
            rest = [i for i in range(len(roles)) if i not in chosen]
            chosen.append(
                max(
                    rest, key=lambda i: len(self.rd.iface.links(r, tuple(chosen), (i,)))
                )
            )
        self.orders[r, start] = tuple(chosen)
        return self.orders[r, start]

    def features(self, r, seq, paths, widths):
        count = len(paths)
        self.stats["prefix_vector_reads"] += count * len(seq)
        h = np.zeros((count, WIDTH), np.float32)
        for d, j in enumerate(seq):
            v = self.bank(self.roles[r][j]).vec[paths[:, d]]
            h[:, :16] += v / len(seq)
            if d == 0:
                h[:, 16:28] = v[:, :12]
        # No literal name or Cell id is visible to the predictor.
        spec = self.rd.iface.rules[r]
        ops = [e["op"] for e in spec["effects"]]
        h[:, 28:] = np.broadcast_to(
            np.array(
                [
                    len(self.roles[r]) / 8,
                    len(spec["query"]) / 12,
                    len(ops) / 12,
                    len(seq) / 8,
                    seq[0] / 8 if seq else -1,
                    float(spec["metadata"]["seminaive"]),
                    ops.count("let") / 8,
                    ops.count("set") / 8,
                    ops.count("union") / 8,
                    ops.count("copy") / 8,
                    ops.count("hide") / 8,
                    len(self.rd.iface.roles[r][seq[-1]][1]) / 8 if seq else 0,
                    0,
                ],
                np.float32,
            ),
            (count, 13),
        )
        h[:, -1] = np.log1p(widths) / 8
        return h

    def window(self, r, seq, j, paths):
        dst = self.bank(self.roles[r][j])
        links = self.rd.iface.links(r, tuple(seq), (j,))
        if not links or not len(dst.ports):
            return (
                None,
                np.zeros(len(paths), dtype=np.int64),
                np.full(len(paths), len(dst.ports), dtype=np.int64),
            )
        i, col, _, right = links[0]
        src = self.bank(self.roles[r][i])
        # The shared vector encoder's LSH address (including collisions).
        self.stats["query_field_reads"] += len(paths)
        code = src.codes[paths[:, seq.index(i)], col]
        if right not in dst.fields:
            self.stats["posting_index_reads"] += len(dst.ports)
        order, offsets = dst.postings(right)
        return order, offsets[code], offsets[code + 1] - offsets[code]


def ranges(pred, n):
    # Predict two relative addresses. All intervening lanes are explicit outputs
    # of the range instruction; PAGE only bounds the transport chunk.
    uv = (1 / (1 + np.exp(-np.clip(pred[:, 1:], -40, 40)))) * (n[:, None] - 1).clip(0)
    pos = np.rint(uv).astype(np.int64)
    return pos.min(1), pos.max(1)


def pages(start, length):
    end = length.cumsum()
    if not len(end):
        return
    base = end - length
    for i in range(0, int(end[-1]), PAGE):
        linear = np.arange(i, min(i + PAGE, int(end[-1])))
        owner = np.searchsorted(end, linear, side="right")
        yield owner, start[owner] + linear - base[owner]
