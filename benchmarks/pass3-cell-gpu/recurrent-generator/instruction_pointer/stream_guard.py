"""Joint proposal readout and sparse addressing over trained field-vector buckets."""

from collections import Counter
from time import perf_counter

import torch
from torch import nn

from cell_stream import CellStream
from recursive_agent import WIDTH

FEATURES = 5 * WIDTH + 4


class JointReadout(nn.Sequential):
    def __init__(self):
        super().__init__(nn.Linear(FEATURES, 48), nn.Tanh(), nn.Linear(48, 1))


class GuardStream(CellStream):
    def __init__(self, *args, study):
        super().__init__(*args)
        self.study = study
        self.locations = {}
        self.postings = {}

    def children(self, paths, depth, block):
        if not self.study.bits or not self.links[depth]:
            yield from super().children(paths, depth, block)
            return
        # Compile one typed neural lookup from the first shared role/field.
        # A bucket can contain unequal values. No scalar guard or raw value join.
        a, col, right = self.links[depth][0]
        bits = self.study.bits
        mask = (1 << bits) - 1
        if depth not in self.postings:
            prepared_at = perf_counter()
            codes = torch.tensor(
                [self.rd.index.rows[k][2][right] & mask for k in self.roles[depth]]
            )
            n_codes = 1 << bits
            positions = torch.arange(len(codes))
            if self.study.delta_buckets and self.semi and depth + 1 == len(self.roles):
                young = self.tables[depth][0]
                positions = torch.cat((positions, positions[young]))
                codes = torch.cat((codes, codes[young] + n_codes))
                n_codes *= 2
            order = positions[codes.argsort(stable=True)]
            offsets = torch.cat(
                (
                    torch.zeros(1, dtype=torch.long),
                    codes.bincount(minlength=n_codes).cumsum(0),
                )
            )
            if self.study.symmetric:
                query_codes = torch.tensor(
                    [self.rd.index.rows[k][2][col] & mask for k in self.roles[a]]
                )
            else:
                query_codes = self.rd.index.code(self.tables[a][2][:, col]) & mask
            self.stats["index_items"] += len(codes) + len(query_codes)
            self.postings[depth] = order, offsets, query_codes
            self.stats["bucket_build_seconds"] += perf_counter() - prepared_at
        order, offsets, query_codes = self.postings[depth]
        code = query_codes[paths[:, a]]
        if self.study.delta_buckets and self.semi and depth + 1 == len(self.roles):
            prefix_fresh = torch.stack(
                [self.tables[i][0][paths[:, i]] for i in range(depth)]
            ).any(0)
            code = code + (~prefix_fresh).long() * (1 << bits)
        self.stats["bucket_probes"] += len(code)
        ends = (offsets[code + 1] - offsets[code]).cumsum(0)
        starts = torch.cat((ends.new_zeros(1), ends[:-1]))
        total = int(ends[-1])
        self.stats["bucket_items"] += total
        for i in range(0, total, block):
            ix = torch.arange(i, min(i + block, total))
            parent = torch.searchsorted(ends, ix, right=True)
            yield parent, order[offsets[code[parent]] + ix - starts[parent]]

    def features(self, p):
        # Static operand roles select individually encoded fields. Pool across
        # primitive instructions and retain argument order. No arithmetic result
        # or verifier response enters a feature.
        n = len(p)
        zero = torch.zeros(n, WIDTH)
        contexts = [self.tables[j][1][p[:, j]] for j in range(p.shape[1])]
        roles = self.rd.iface.roles[self.rule]
        if not self.locations:
            for j, role in enumerate(self.order):
                for col, slot in enumerate(roles[role][1]):
                    if slot is not None:
                        self.locations.setdefault(slot, (j, col))
        channels = [[], [], []]
        count = 0
        for atom in self.rd.iface.rules[self.rule]["query"]:
            if "primitive" not in atom["call"]:
                continue
            count += 1
            for j, arg in enumerate(atom["args"]):
                pos = self.locations.get(arg.get("slot"))
                if pos is not None:
                    i, c = pos
                    channel = 2 if j == len(atom["args"]) - 1 else min(j, 1)
                    channels[channel].append(self.tables[i][3][p[:, i], c])
        ctx = torch.stack(contexts)
        meta = torch.tensor(
            [
                len(self.roles) / 8,
                count / 8,
                sum(map(len, self.links)) / 8,
                len(self.locations) / 16,
            ]
        ).expand(n, -1)
        return torch.cat(
            [
                ctx.mean(0),
                ctx.amax(0),
                *[torch.stack(ch).mean(0) if ch else zero for ch in channels],
                meta,
            ],
            1,
        )

    def terminal(self, paths):
        if not len(paths) or self.study.head is None and not self.study.collect:
            return paths
        x = self.features(paths)
        self.stats["joint_scores"] += len(x)
        if self.study.collect:
            self.study.pending.extend(x.unbind())
            return paths
        return paths[self.study.head(x).flatten() >= self.study.threshold]


class Study:
    def __init__(
        self,
        bits=0,
        head=None,
        threshold=0.0,
        collect=False,
        symmetric=False,
        delta_buckets=False,
    ):
        self.bits, self.head, self.threshold, self.collect = (
            bits,
            head,
            threshold,
            collect,
        )
        self.symmetric = symmetric
        self.delta_buckets = delta_buckets
        self.pending = []
        self.data = []
        self.labels = []
        self.counts = Counter()

    def stream(self, *args):
        return GuardStream(*args, study=self)

    def verdicts(self, batch, replies, rd):
        if not self.collect:
            return
        keep = [
            (q, v) for q, (_, v) in zip(batch, replies, strict=True) if q["parents"]
        ]
        n = len(keep)
        assert len(self.pending) >= n
        for x, (q, v) in zip(self.pending[:n], keep, strict=True):
            self.counts[v] += 1
            # Repeated valid bindings and stale observations carry separate
            # semantics. Train validity on accepted / guard / binding only.
            if v in ("accepted", "guard", "binding"):
                self.data.append(x)
                self.labels.append(v == "accepted")
        del self.pending[:n]
