"""Isolated symbolic and neural request generators on sealed owner projections."""

from collections import Counter, defaultdict
from time import perf_counter

import numpy as np
import torch

from composition_relation import Interfaces, Relation, Store
from field_retrieval import FieldEncoder, FieldIndex
from relation_cases import request
from retrieval_panels import compose_scores, layout_sides, parents, retrieve_owners


class EqualityIndex:
    def __init__(self):
        self.rows = {}
        self.buckets = defaultdict(set)
        self.writes = self.removes = 0

    def advance(self, frame):
        for addr in frame["retired"]:
            k = addr["token"], addr["op"]
            table, old = self.rows.pop(k)
            for col, h in enumerate(old):
                self.remove(k, (table, col, h))
        for addr, row in frame["updates"]:
            k = addr["token"], addr["op"]
            tab = row["table"]
            hs = tuple(row["hashes"])
            before = self.rows.get(k)
            if before and (tab != before[0] or len(hs) != len(before[1])):
                raise ValueError("port type changed")
            for col, h in enumerate(hs):
                if before:
                    prev = before[1][col]
                    if prev == h:
                        continue
                    self.remove(k, (tab, col, prev))
                self.buckets[tab, col, h].add(k)
                self.writes += 1
            self.rows[k] = tab, hs

    def remove(self, k, bucket):
        self.buckets[bucket].remove(k)
        self.removes += 1
        if not self.buckets[bucket]:
            del self.buckets[bucket]


class LocalJoin:
    def __init__(self, store, index, rid, src, dst):
        self.index = index
        self.store = store
        self.src = src
        self.dst = dst
        roles = store.iface.roles[rid]
        links = []
        self.local = []
        for side in [src, dst] if dst else [src]:
            first = {}
            keep = np.ones(len(side.rows), dtype=bool)
            for i, r in enumerate(side.roles):
                for col, v in enumerate(roles[r][1]):
                    if v is None:
                        continue
                    if v in first:
                        j, c = first[v]
                        keep &= np.array(
                            [
                                index.rows[row[i]][1][col] == index.rows[row[j]][1][c]
                                for row in side.rows
                            ]
                        )
                    else:
                        first[v] = i, col
            self.local.append(keep)
            links.append(first)
        self.cross = []
        if dst:
            for v in links[0].keys() & links[1].keys():
                a, x = links[0][v]
                b, y = links[1][v]
                self.cross.append(
                    (a, x, b, y, store.iface.tables.index(roles[dst.roles[b]][0]))
                )
        self.post = defaultdict(list)
        if dst:
            for i, row in enumerate(dst.rows):
                if self.local[1][i]:
                    for pos, addr in enumerate(row):
                        self.post[pos, addr].append(i)

    def read(self, i, stats):
        if not self.local[0][i]:
            return np.empty(0, dtype=int)
        if not self.dst:
            return np.array([0])
        if not self.cross:
            return np.flatnonzero(
                self.local[1]
                & (self.dst.owners != self.src.owners[i])
                & (self.dst.first > self.src.first[i])
            )
        choices = []
        for a, x, b, y, tab in self.cross:
            value = self.index.rows[self.src.rows[i][a]][1][x]
            bucket = self.index.buckets.get((tab, y, value), ())
            choices.append((b, bucket))
            stats["index_lookups"] += 1
        b, bucket = min(choices, key=lambda c: len(c[1]))
        stats["postings_visited"] += len(bucket)
        matches = [j for addr in bucket for j in self.post.get((b, addr), ())]
        stats["projected_postings"] += len(matches)
        # Check each remaining shared variable against the same projected partner tuple.
        result = np.array(sorted(matches), dtype=int)
        result = result[
            (self.dst.owners[result] != self.src.owners[i])
            & (self.dst.first[result] > self.src.first[i])
        ]
        for pos, candidates in choices:
            result = np.array(
                [j for j in result if self.dst.rows[j][pos] in candidates], dtype=int
            )
        return result


class NeuralRead:
    def __init__(self, store, index, rid, src, dst):
        self.src = src
        self.dst = dst
        self.index = index
        self.links = (
            [
                (
                    src.roles.index(a),
                    x,
                    dst.roles.index(b),
                    y,
                    store.iface.tables.index(store.iface.roles[rid][b][0]),
                )
                for a, x, b, y in store.iface.links(rid, src.roles, dst.roles)
            ]
            if dst
            else []
        )
        if dst and not self.links:
            pools = {
                t: torch.nn.functional.normalize(
                    torch.cat(list(index.owners[t].values())).mean(0), dim=0
                )
                for t in set(dst.owners)
            }
            self.pooled = torch.stack([pools[t] for t in dst.owners])

    def read(self, i, ix, stats, rng):
        if not self.dst:
            return ix
        row = self.src.rows[i]
        probes = [
            (self.index.queries[row[a]][x], tab, y) for a, x, b, y, tab in self.links
        ]
        if probes:
            owners = set()
            for query, tab, col in probes:
                code = self.index.code(query).item()
                for key in (code, *[code ^ (1 << bit) for bit in range(8)]):
                    entries = self.index.buckets.get((tab, col, key), ())
                    stats["postings_visited"] += len(entries)
                    stats["index_lookups"] += 1
                    owners.update(k[0] for k in entries)
            allowed = ix[np.isin(self.dst.owners[ix], list(owners))]
            if not len(allowed):
                return allowed
            scores = np.zeros(len(allowed), dtype=np.float32)
            for (q, _, _), (_, _, b, y, _) in zip(probes, self.links, strict=True):
                bank = torch.stack(
                    [self.index.keys[self.dst.rows[j][b]][y] for j in allowed]
                )
                scores += (bank @ q).numpy() / len(probes)
        else:
            allowed = ix
            q = torch.nn.functional.normalize(
                torch.cat(
                    [self.index.queries[k] for k in self.index.owners[row[0][0]]]
                ).mean(0),
                dim=0,
            )
            scores = (self.pooled[ix] @ q).numpy()
        stats["retrieval_vector_scores"] += len(allowed) * max(1, len(probes))
        chosen = retrieve_owners(
            scores,
            np.arange(len(allowed)),
            self.dst.owners[allowed],
            rng.random(len(allowed)),
        )
        return allowed[chosen]


class Generator:
    @torch.no_grad()
    def __init__(self, root, program, arm):
        self.arm = arm
        self.store = Store(Interfaces(program))
        self.count = Counter()
        self.times = Counter()
        self.rng = np.random.default_rng(779)
        self.model = None
        if arm in ("C", "D"):
            self.model = Relation().eval()
            self.model.load_state_dict(
                torch.load(
                    root / "relation-experiment/train/model.pt", weights_only=True
                )
            )
        if arm == "D":
            enc = FieldEncoder().eval()
            enc.load_state_dict(
                torch.load(root / "structured-retrieval/field.pt", weights_only=True)
            )
            self.index = FieldIndex(enc)
        else:
            self.index = EqualityIndex()

    def symbolic_projections(self, rid, roles, limit):
        schema = self.store.iface.roles[rid]
        tabs = [
            self.store.by_table[self.store.iface.tables.index(schema[r][0])]
            for r in roles
        ]
        rows = []
        for owner in min(tabs, key=len):
            if not all(owner in tab for tab in tabs):
                continue

            def extend(n, prefix, bindings):
                if n == len(roles):
                    rows.append(tuple(prefix))
                    if len(rows) > limit:
                        raise OverflowError(
                            f"rule {rid}, roles {roles}: over {limit} locally consistent projections"
                        )
                    return
                for pc, row in tabs[n][owner].items():
                    self.count["local_ports_visited"] += 1
                    bound = bindings.copy()
                    for slot, value in zip(
                        schema[roles[n]][1], row["hashes"], strict=True
                    ):
                        if slot is not None and bound.setdefault(slot, value) != value:
                            break
                    else:
                        extend(n + 1, (*prefix, (owner, pc)), bound)

            extend(0, (), {})
        return rows

    def advance(self, frame):
        start = perf_counter()
        self.store.advance(frame)
        self.times["store"] += perf_counter() - start
        start = perf_counter()
        writes = self.index.writes
        removes = self.index.removes
        self.index.advance(frame)
        elapsed = perf_counter() - start
        self.times["index"] += elapsed
        return elapsed, self.index.writes - writes, self.index.removes - removes

    @torch.no_grad()
    def issue(
        self, frame, bootstrap=False, rank_all=False, remaining=None, live=False, frontier=None
    ):
        result = {}
        prepared = 0
        for rid, wm in frame["rules"]:
            if not self.store.iface.roles[rid]:
                if bootstrap and (
                    wm == 0 or not self.store.iface.rules[rid]["metadata"]["seminaive"]
                ):
                    prepared += 1
                    result[rid, "empty"] = [request(frame["run"], rid, (), self.store)]
                if remaining is not None and prepared >= remaining:
                    return result
                continue

            def events():
                pairs = layout_sides(
                    self.store,
                    self.model,
                    rid,
                    wm,
                    250000 if live else float("inf"),
                    project=None if self.arm == "D" else self.symbolic_projections,
                )
                while True:
                    start = perf_counter()
                    sides = next(pairs, None)
                    self.times["prepare"] += perf_counter() - start
                    if sides is None:
                        return
                    a, b, _ = sides
                    if frontier is not None:
                        frontier.update(a.owners.tolist())
                        if b is not None:
                            frontier.update(b.owners.tolist())
                    for src, dst in [(a, b), (b, a)] if b else [(a, None)]:
                        fresh = np.flatnonzero(
                            src.first < len(self.store.iface.roles[rid])
                        )
                        if not len(fresh):
                            continue
                        t = perf_counter()
                        reader = (NeuralRead if self.arm == "D" else LocalJoin)(
                            self.store, self.index, rid, src, dst
                        )
                        self.times["retrieval"] += perf_counter() - t
                        for i in fresh:
                            yield src, i, dst, reader

            for src, i, dst, reader in events():
                self.count["events"] += 1
                start = perf_counter()
                if self.arm == "D":
                    ix = (
                        np.flatnonzero(
                            (dst.owners != src.owners[i]) & (dst.first > src.first[i])
                        )
                        if dst
                        else np.array([0])
                    )
                    self.count["typed_positions_tested"] += len(dst.rows) if dst else 1
                    ids = reader.read(i, ix, self.count, self.rng)
                else:
                    ids = reader.read(i, self.count)
                self.times["retrieval"] += perf_counter() - start
                self.count["candidates"] += len(ids)
                if not len(ids):
                    continue
                start = perf_counter()
                if self.model is not None:
                    scores = compose_scores(src, i, dst, ids)
                    self.count["compose_scores"] += len(ids)
                else:
                    scores = (
                        self.rng.random(len(ids))
                        if self.arm == "B"
                        else np.zeros(len(ids))
                    )
                order = np.arange(len(ids))
                if not rank_all and self.arm != "A":
                    order = np.lexsort((self.rng.random(len(ids)), -scores))[:8]
                self.times["rank"] += perf_counter() - start
                if remaining is not None:
                    order = order[: remaining - prepared]
                prepared += len(order)
                if live and prepared > 250000:
                    raise OverflowError(
                        f"rule {rid}: {prepared} or more complete requests in one Run"
                    )
                values = []
                for n in order:
                    packet = request(
                        frame["run"], rid, parents(src, i, dst, ids[n]), self.store
                    )
                    values.append((float(scores[n]), packet) if rank_all else packet)
                result[rid, src.roles, src.rows[i]] = values
                if remaining is not None and prepared >= remaining:
                    return result
        return result
