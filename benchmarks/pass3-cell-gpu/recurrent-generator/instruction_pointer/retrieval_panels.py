"""Partition the entire typed delta domain without dropping large layouts."""

import math
from dataclasses import dataclass

import numpy as np
import torch

from composition_relation import encode


@dataclass
class Side:
    roles: tuple
    rows: list
    owners: np.ndarray
    first: np.ndarray
    vectors: torch.Tensor | None
    positions: dict


def make_side(store, model, rid, roles, other, rows, wm, side):
    parts = []
    for start in range(0, len(rows) if model is not None else 0, 256):
        x, f = encode(store, rid, roles, rows[start : start + 256], wm, other)
        parts.append(
            model.vectors(x, f, side) if other else model.unary(model.encoder(x))
        )
    first = np.array(
        [
            min(
                (
                    i
                    for i, key in zip(roles, row)
                    if store.visible[key]["version"] >= wm
                    or not store.iface.rules[rid]["metadata"]["seminaive"]
                ),
                default=len(store.iface.roles[rid]),
            )
            for row in rows
        ]
    )
    return Side(
        roles,
        rows,
        np.array([r[0][0] for r in rows]),
        first,
        torch.cat(parts) if parts else None,
        {r: i for i, r in enumerate(rows)},
    )


def layout_sides(store, model, rid, wm, limit=math.inf, project=None):
    cache = {}
    for left, right in store.iface.layouts(rid):
        for side in (left, right):
            if side and side not in cache:
                cache[side] = (project or store.projections)(rid, side, limit)
                if cache[side] is None:
                    raise OverflowError(
                        f"rule {rid}, roles {side}: more than {limit} typed projections"
                    )
        a = cache[left]
        b = cache[right] if right else [()]
        if not a or not b:
            continue
        within_old = max(len(a), len(b)) <= 2048 and len(a) * len(b) <= 65536
        aa = make_side(store, model, rid, left, right, a, wm, 0)
        bb = make_side(store, model, rid, right, left, b, wm, 1) if right else None
        yield aa, bb, within_old


def panels(store, model, rid, wm):
    events = []
    old_budget = 0
    for aa, bb, within_old in layout_sides(store, model, rid, wm):
        for src, dst in [(aa, bb), (bb, aa)] if bb else [(aa, None)]:
            for i in np.flatnonzero(src.first < len(store.iface.roles[rid])):
                ix = (
                    np.flatnonzero(
                        (dst.owners != src.owners[i]) & (dst.first > src.first[i])
                    )
                    if dst
                    else np.array([0])
                )
                if not len(ix):
                    continue
                if within_old and old_budget + len(ix) <= 16384:
                    old_budget += len(ix)
                events.append((src, i, dst, ix, within_old))
    return events, old_budget


def parents(src, i, dst, j):
    keys = [None] * (len(src.roles) + (len(dst.roles) if dst else 0))
    for role, key in zip(src.roles, src.rows[i]):
        keys[role] = key
    if dst:
        for role, key in zip(dst.roles, dst.rows[j]):
            keys[role] = key
    return tuple(keys)


def compose_scores(src, i, dst, ix):
    if not dst:
        return src.vectors[i].numpy()
    q = src.vectors[i]
    bank = dst.vectors
    return torch.cat(
        [(bank[j] * q).sum(-1) for j in np.array_split(ix, (len(ix) + 255) // 256)]
    ).numpy()


def topk(score, ids, k):
    if len(ids) <= k:
        return ids
    values = score[ids]
    cut = np.partition(values, -k - 1)[-k - 1]
    return ids[values > cut]


class InterfaceRead:
    def __init__(self, index, store, rid, src, dst):
        self.index = index
        self.dst = dst
        links = store.iface.links(rid, src.roles, dst.roles)
        self.links = [
            (
                src.roles.index(a),
                i,
                dst.roles.index(b),
                j,
                store.iface.tables.index(store.iface.roles[rid][b][0]),
            )
            for a, i, b, j in links
        ]
        self.bank = [
            torch.stack([index.keys[row[d]][j] for row in dst.rows])
            for _, _, d, j, _ in self.links
        ]
        self.raw = [
            np.array(
                [store.visible[row[d]]["hashes"][j] for row in dst.rows],
                dtype=np.uint64,
            )
            for _, _, d, j, _ in self.links
        ]
        self.pooled = {}
        for owner in set(dst.owners):
            self.pooled[owner] = torch.nn.functional.normalize(
                torch.cat(list(index.owners[owner].values())).mean(0), dim=0
            )
        self.single = torch.stack([self.pooled[t] for t in dst.owners])

    def query(self, store, src, i, ix):
        row = src.rows[i]
        owner = row[0][0]
        q = torch.nn.functional.normalize(
            torch.cat([self.index.queries[k] for k in self.index.owners[owner]]).mean(
                0
            ),
            dim=0,
        )
        single = (self.single[ix] @ q).numpy()
        if not self.links:
            return single, single, np.arange(len(ix)), single, np.arange(len(ix))
        probes = []
        eq = np.ones(len(ix), dtype=bool)
        field = np.zeros(len(ix), dtype=np.float32)
        for n, (a, k, _, _, tab) in enumerate(self.links):
            query = self.index.queries[row[a]][k]
            field += (self.bank[n][ix] @ query).numpy() / len(self.links)
            eq &= self.raw[n][ix] == store.visible[row[a]]["hashes"][k]
            probes.append((query, tab, self.links[n][3]))
        owners = self.index.shortlist(probes)
        ann = (
            np.flatnonzero(np.isin(self.dst.owners[ix], list(owners)))
            if owners
            else np.empty(0, dtype=int)
        )
        ann_scores = np.zeros(len(ann), dtype=np.float32)
        for bank, (query, _, _) in zip(self.bank, probes, strict=True):
            ann_scores += (bank[ix[ann]] @ query).numpy() / len(probes)
        return single, field, ann, ann_scores, np.flatnonzero(eq)


def domain_size(store, rid, wm):
    """Count type-visible ordered projections using owner cardinalities alone."""
    cache = {}

    def counts(roles):
        if roles not in cache:
            tables = [
                store.by_table[store.iface.tables.index(store.iface.roles[rid][i][0])]
                for i in roles
            ]
            rows = {}
            for owner in min(tables, key=len):
                if all(owner in t for t in tables):
                    n = math.prod(len(t[owner]) for t in tables)
                    old = (
                        math.prod(
                            sum(row["version"] < wm for row in t[owner].values())
                            for t in tables
                        )
                        if store.iface.rules[rid]["metadata"]["seminaive"]
                        else 0
                    )
                    rows[owner] = (n, old)
            cache[roles] = (
                rows,
                sum(n for n, _ in rows.values()),
                sum(o for _, o in rows.values()),
            )
        return cache[roles]

    total = 0
    for left, right in store.iface.layouts(rid):
        a, n, old = counts(left)
        if not right:
            total += n - old
            continue
        b, m, other = counts(right)
        total += n * m - old * other
        for owner in a.keys() & b.keys():
            x, u = a[owner]
            y, v = b[owner]
            total -= x * y - u * v
    return total


def retrieve_owners(scores, positions, owners, tie, limit=32):
    """Rank owners by their best role-compatible projection, then expose their mappings."""
    ranked = positions[np.lexsort((tie[positions], -scores))]
    if not len(ranked):
        return ranked
    _, first = np.unique(owners[ranked], return_index=True)
    selected = owners[ranked[np.sort(first)[:limit]]]
    return ranked[np.isin(owners[ranked], selected)]
