"""Shared schema-conditioned inner products over visible Cell owners and static op projections."""

from collections import defaultdict
from functools import lru_cache
from itertools import product
import math

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

from cell_composition_census import inventory
from higher_cell import fingerprint


class Interfaces:
    def __init__(self, program):
        self.receipt_contract = program.get("receipt_contract")
        self.exports, self.tables = inventory(program)
        self.rules = program["recipe"]["rules"]
        self.roles = [
            [
                (a["call"]["table"], tuple(v.get("slot") for v in a["args"]))
                for a in r["query"]
                if "table" in a["call"]
            ]
            for r in self.rules
        ]
        self.signature = {
            ("generated", i): fingerprint(r) for i, r in enumerate(self.rules)
        }
        self.signature.update(
            {
                ("initial", t["name"]): fingerprint(t)
                for t in program["recipe"]["tables"]
            }
        )
        self.signature.update(
            {
                ("repair", m["table"]): fingerprint(m)
                for m in program["merge_programs"]["programs"]
            }
        )

    @lru_cache(None)
    def layouts(self, rid):
        roles = self.roles[rid]
        allroles = tuple(range(len(roles)))
        if not roles:
            return ()
        mask = (1 << len(roles)) - 1
        patterns = {
            sum(1 << i for i, (table, _) in enumerate(roles) if table in out)
            for out in {frozenset(x.values()) for x in self.exports.values()}
        }
        partitions = set()
        if mask in patterns:
            partitions.add(mask)
        for a in patterns:
            if not a & 1:
                continue
            for b in patterns:
                if a | b != mask:
                    continue
                optional = a & b & ~1
                fixed = (mask ^ b) | 1
                sub = optional
                while True:
                    partitions.add(fixed | sub)
                    if sub == 0:
                        break
                    sub = (sub - 1) & optional
        return tuple(
            (
                tuple(i for i in allroles if part >> i & 1),
                tuple(i for i in allroles if not part >> i & 1),
            )
            for part in sorted(partitions)
        )

    def key(self, rid, keys, types):
        groups = {}
        spec = []
        for t, pc in keys:
            group = groups.setdefault(t, len(groups))
            kind, label = types[t]
            spec.append((group, kind, self.signature[kind, label], pc))
        return self.signature["generated", rid], tuple(spec)

    @lru_cache(None)
    def links(self, rid, left, right):
        roles = self.roles[rid]
        return tuple(
            (a, i, b, j)
            for a in left
            for b in right
            if a != b
            for i, x in enumerate(roles[a][1])
            for j, y in enumerate(roles[b][1])
            if x is not None and x == y
        )


class Store:
    def __init__(self, iface, rename_seed=None):
        import random

        self.rng = random.Random(rename_seed) if rename_seed is not None else None
        self.names = {}
        self.original = {}
        self.iface = iface
        self.types = {}
        self.visible = {}
        self.by_table = defaultdict(lambda: defaultdict(dict))

    def alias(self, t):
        if self.rng is None:
            return t
        if t not in self.names:
            name = self.rng.getrandbits(63)
            while name in self.original:
                name = self.rng.getrandbits(63)
            self.names[t] = name
            self.original[name] = t
        return self.names[t]

    def advance(self, frame):
        for req in frame["accepted"]:
            self.types[self.alias(req["token"])] = ("generated", req["rule"])
        for ev in frame["repair_events"]:
            self.types[self.alias(ev["token"])] = (
                "repair",
                self.iface.tables[ev["merge_table"]],
            )
        for addr in frame["retired"]:
            t, pc = self.alias(addr["token"]), addr["op"]
            row = self.visible.pop((t, pc))
            owners = self.by_table[row["table"]]
            del owners[t][pc]
            if not owners[t]:
                del owners[t]
        for addr, row in frame["updates"]:
            t, pc = self.alias(addr["token"]), addr["op"]
            tab = row["table"]
            if addr["token"] < 0 and addr["token"] % 2:
                self.types[t] = ("initial", self.iface.tables[tab])
            if self.iface.exports[self.types[t]].get(pc) != self.iface.tables[tab]:
                raise ValueError("bad static port")
            self.visible[t, pc] = row
            self.by_table[tab][t][pc] = row

    def projections(self, rid, roles, limit=2048):
        tables = [
            self.by_table[self.iface.tables.index(self.iface.roles[rid][i][0])]
            for i in roles
        ]
        owners = min(tables, key=len)
        rows = []
        for owner in owners:
            if all(owner in t for t in tables):
                if len(rows) + math.prod(len(t[owner]) for t in tables) > limit:
                    return None
                rows.extend(
                    tuple((owner, pc) for pc in pcs)
                    for pcs in product(*(t[owner] for t in tables))
                )
        return rows


@lru_cache(maxsize=32768)
def bits(value):
    return (
        np.unpackbits(np.array([value], dtype=">u8").view(np.uint8)).astype("float32")
        * 2
        - 1
    )


def encode(store, rid, roles, rows, wm, other):
    iface = store.iface
    cross = iface.links(rid, roles, other)
    if roles and other and roles[0] > other[0]:
        cross = tuple((b, j, a, i) for a, i, b, j in iface.links(rid, other, roles))
    inside = iface.links(rid, roles, roles)
    feats = []
    fields = []
    for row in rows:
        owner = row[0][0]
        tp = store.types[owner]
        out = iface.exports[tp]
        records = {r: store.visible[k] for r, k in zip(roles, row)}
        pcs = [k[1] for k in row]
        features = [
            len(roles) / 8,
            len(other) / 8,
            len(out) / 32,
            len(set(pcs)) / 8,
            float(tp[0] == "initial"),
            float(tp[0] == "repair"),
            sum(math.sin(p) for p in pcs) / len(pcs),
            sum(math.cos(p) for p in pcs) / len(pcs),
            sum(r["version"] >= wm for r in records.values()) / len(row),
            sum(r["forwarded"] for r in records.values()) / len(row),
            len(cross) / 16,
            len(inside) / 16,
            sum(len(r["hashes"]) for r in records.values()) / len(row) / 8,
            len(set(iface.roles[rid][i][0] for i in roles)) / len(roles),
        ]
        feats.append(features)
        # The opposite side must pack its fields in the same edge order.
        fields.append([bits(records[a]["hashes"][i]) for a, i, b, j in cross])
    return torch.tensor(feats), torch.from_numpy(
        np.asarray(fields, dtype="float32").reshape(len(rows), len(cross) * 64)
    )


class Relation(nn.Module):
    def __init__(self):
        super().__init__()
        self.encoder = nn.Sequential(nn.Linear(14, 24), nn.Tanh(), nn.Linear(24, 16))
        self.q = nn.Linear(16, 12)
        self.k = nn.Linear(16, 12)
        self.unary = nn.Linear(16, 1)
        self.scale = nn.Parameter(torch.tensor(2.0))

    def vectors(self, x, f, side):
        h = self.encoder(x)
        projected = self.q(h) if side == 0 else self.k(h)
        return torch.cat(
            (projected, f * F.softplus(self.scale) / math.sqrt(max(f.shape[-1], 1))), -1
        )
