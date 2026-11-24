"""Neural decoding over typed owner/op positions in an immutable native Run."""

from math import log1p, prod
from time import perf_counter

import torch

from recursive_agent import WIDTH

BLOCK = 2048


class CellStream:
    """One generator frame is a resumable Cartesian cursor. Only the model scores evidence."""

    def __init__(self, reader, model, rule, watermark, stats):
        self.rd, self.model, self.rule, self.wm, self.stats = (
            reader,
            model,
            rule,
            watermark,
            stats,
        )
        self.order = reader.order(rule)
        self.roles = []
        self.links = []
        self.semi = reader.iface.rules[rule]["metadata"]["seminaive"]
        for j, role in enumerate(self.order):
            tab = reader.tabs[reader.iface.roles[rule][role][0]]
            self.roles.append(sorted(reader.live[tab]))
            self.links.append(
                [
                    (self.order.index(a), c, col)
                    for a, c, _, col in reader.iface.links(
                        rule, self.order[:j], (role,)
                    )
                ]
            )
        self.tables = []
        self.prepared = False

    def prepare(self):
        if self.prepared:
            return
        idx = self.rd.index
        for j, ports in enumerate(self.roles):
            rows = [self.rd.store.visible[k] for k in ports]
            age = torch.tensor(
                [r["version"] >= self.wm for r in rows], dtype=torch.bool
            )
            self.stats["interface_reads"] += len(ports)
            bank = torch.stack([idx.keys[k].mean(0) for k in ports])
            q = torch.stack([idx.queries[k] for k in ports])
            k = torch.stack([idx.keys[k] for k in ports])
            extra = torch.tensor(
                [
                    [
                        j / 8,
                        len(self.roles) / 8,
                        float(fresh),
                        min(1, log1p(max(0, self.wm - r["version"])) / 8),
                        float(r["forwarded"]),
                        float(self.rd.store.types[p[0]][0] == "initial"),
                        float(self.rd.store.types[p[0]][0] == "repair"),
                        min(p[1], 64) / 64,
                        len(r["hashes"]) / 8,
                    ]
                    for p, r, fresh in zip(ports, rows, age.tolist(), strict=True)
                ]
            )
            self.tables.append((age, bank, q, k, extra))
        self.prepared = True

    def local(self, depth, paths):
        _, bank, _, key, extra = self.tables[depth]
        c = paths[:, -1]
        dots = [
            (self.tables[a][2][paths[:, a], col] * key[c, right]).sum(1)
            for a, col, right in self.links[depth]
        ]
        if dots:
            d = torch.stack(dots, 1)
            evidence = torch.stack([d.mean(1), d.amin(1), d.amax(1)], 1)
        else:
            evidence = bank.new_zeros(len(c), 3)
        return torch.cat((bank[c], evidence, extra[c]), 1)

    def logits(self, h, depth, p):
        x = self.local(depth, p)
        z = self.model.cell(self.model.encode(x), h)
        return self.model.score(z).flatten() + 2 * x[:, WIDTH], z

    def children(self, paths, depth, block):
        size = len(self.roles[depth])
        for start in range(0, len(paths) * size, block):
            ix = torch.arange(start, min(start + block, len(paths) * size))
            yield ix // size, ix % size

    def terminal(self, paths):
        return paths

    def batches(self, mode, cutoff, deadline, block=BLOCK):
        if not self.roles:
            if self.wm == 0 or not self.semi:
                yield [()]
            return
        if not all(self.roles):
            return
        self.prepare()
        if self.semi and not any(t[0].any() for t in self.tables):
            return
        self.stats["typed_products"] += prod(map(len, self.roles))

        def extend(p, h, ok, fresh, j):
            last = j + 1 == len(self.roles)
            for parent, col in self.children(p, j, block):
                if perf_counter() > deadline:
                    raise TimeoutError
                self.stats["traversed_positions"] += len(col)
                now = fresh[parent] | self.tables[j][0][col]
                if self.semi and last:
                    parent, col, now = parent[now], col[now], now[now]
                if not len(col):
                    continue
                paths = torch.cat((p[parent], col[:, None]), 1)
                s, z = self.logits(h[parent], j, paths)
                keep = ok[parent] & (s >= cutoff)
                self.stats["visits"] += len(s)
                if not j:
                    self.stats["root_scored"] += len(s)
                if last:
                    self.stats["tuple_scored"] += len(s)
                    out = [
                        tuple(self.roles[n][idx] for n, idx in enumerate(row))
                        for row in self.terminal(paths[keep]).tolist()
                    ]
                    if out:
                        yield out
                elif mode == "dense":
                    yield from extend(paths, z, keep, now, j + 1)
                elif keep.any():
                    yield from extend(
                        paths[keep], z[keep], keep[keep], now[keep], j + 1
                    )

        h = self.model.start(self.rd.meta(self.rule))[None, :]
        yield from extend(
            torch.empty((1, 0), dtype=torch.long),
            h,
            torch.ones(1, dtype=torch.bool),
            torch.zeros(1, dtype=torch.bool),
            0,
        )

    def named(self, paths, cutoff):
        """Offline score of given teacher witnesses, with exactly the deployed predicate."""
        self.prepare()
        lookup = [{k: i for i, k in enumerate(ports)} for ports in self.roles]
        p = torch.tensor(
            [[m[k] for m, k in zip(lookup, seq, strict=True)] for seq in paths]
        )
        h = self.model.start(self.rd.meta(self.rule)).expand(len(p), -1)
        alive = torch.ones(len(p), dtype=torch.bool)
        for j in range(len(self.roles)):
            s, h = self.logits(h, j, p[:, : j + 1])
            alive &= s >= cutoff
        return alive.tolist()
