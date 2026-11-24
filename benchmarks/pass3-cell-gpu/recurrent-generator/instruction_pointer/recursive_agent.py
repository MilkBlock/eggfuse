"""Shared recurrent owner/port selection on sealed native Cell memory."""

from collections import Counter, OrderedDict, defaultdict
from dataclasses import dataclass, field
from itertools import islice
from math import log1p
from time import perf_counter

import torch
from torch import nn

from composition_relation import Interfaces, Store
from field_retrieval import FieldEncoder, FieldIndex
from relation_cases import request

WIDTH = 24
FANOUT = 4
BEAM = 6
RUN_EXPANSIONS = 96
RUN_PACKETS = 64
VISITS = 128
POOL = 512


class Compose(nn.Module):
    def __init__(self):
        super().__init__()
        self.encode = nn.Sequential(nn.Linear(WIDTH + 12, WIDTH), nn.Tanh())
        self.cell = nn.GRUCell(WIDTH, WIDTH)
        self.score = nn.Sequential(nn.Linear(WIDTH, 24), nn.Tanh(), nn.Linear(24, 1))
        self.prior = nn.Linear(4, WIDTH)
        self.retry = nn.Linear(WIDTH, 1)
        self.activation = nn.Sequential(nn.Linear(8, 16), nn.Tanh(), nn.Linear(16, 1))

    def start(self, meta):
        return self.prior(meta).tanh()

    def forward(self, h, x):
        z = self.cell(self.encode(x), h.expand(len(x), -1))
        return self.score(z).flatten() + 2 * x[:, WIDTH], z


@dataclass
class Obligation:
    rule: int
    prefix: tuple
    tried: set = field(default_factory=set)
    attempts: int = 0
    last: int = 0
    generation: int = 0
    priority: float = 0.0


class Reader:
    def __init__(self, program, root, rename_seed=None):
        self.iface = Interfaces(program)
        self.store = Store(self.iface, rename_seed)
        encoder = FieldEncoder().eval()
        encoder.load_state_dict(
            torch.load(root / "structured-retrieval/field.pt", weights_only=True)
        )
        self.index = FieldIndex(encoder)
        self.count = Counter()
        self.versions = Counter()
        self.live = defaultdict(dict)
        self.orders = {}
        self.metadata = {}
        self.tabs = {t: i for i, t in enumerate(self.iface.tables)}

    @torch.no_grad()
    def advance(self, f):
        changed = set()
        # Training can relabel the entire live address space. Keep typed metadata
        # in the original frame so Store can distinguish initial and repair events.
        frame = f
        if self.store.rng is not None:

            def alias(a):
                return {"token": self.store.alias(a["token"]), "op": a["op"]}

            frame = dict(
                f,
                retired=[alias(a) for a in f["retired"]],
                updates=[(alias(a), row) for a, row in f["updates"]],
            )
        for a in frame["retired"]:
            key = a["token"], a["op"]
            t = self.store.visible[key]["table"]
            self.live[t].pop(key)
            changed.add(t)
        for a, row in frame["updates"]:
            self.live[row["table"]][a["token"], a["op"]] = None
            changed.add(row["table"])
        self.store.advance(f)
        start = perf_counter()
        self.index.advance(frame)
        self.count["index_update_seconds"] += perf_counter() - start
        for t in changed:
            self.versions[t] += 1
        return changed

    def order(self, r):
        if r in self.orders:
            return self.orders[r]
        roles = self.iface.roles[r]
        order = []
        seen = set()
        while len(order) < len(roles):
            j = max(
                (j for j in range(len(roles)) if j not in order),
                key=lambda j: (
                    len(seen.intersection(x for x in roles[j][1] if x is not None)),
                    -j,
                ),
            )
            order.append(j)
            seen.update(x for x in roles[j][1] if x is not None)
        self.orders[r] = tuple(order)
        return self.orders[r]

    def meta(self, r):
        if r in self.metadata:
            return self.metadata[r]
        rule = self.iface.rules[r]
        self.metadata[r] = torch.tensor(
            [
                len(self.order(r)) / 8,
                len(rule["effects"]) / 8,
                len(rule["query"]) / 12,
                float(rule["metadata"]["seminaive"]),
            ]
        )

        return self.metadata[r]

    def rule_state(self, r, wm, run, last):
        sizes = [len(self.live[self.tabs[t]]) for t, _ in self.iface.roles[r]]
        return [
            *self.meta(r).tolist(),
            log1p(min(sizes, default=0)) / 8,
            log1p(max(sizes, default=0)) / 8,
            float(wm == 0),
            min(run - last, 64) / 64,
        ]

    def addresses(self, r, seq):
        parent = [None] * len(seq)
        for i, k in zip(self.order(r), seq):
            parent[i] = k
        return parent

    def read(self, r, prefix, wm, step, exclude=(), cap=VISITS, force=()):
        order = self.order(r)
        dest = order[len(prefix)]
        tab = self.tabs[self.iface.roles[r][dest][0]]
        links = self.iface.links(r, order[: len(prefix)], (dest,))
        probes = [
            (self.index.queries[prefix[order.index(a)]][c], col)
            for a, c, _, col in links
        ]
        if cap == 0:
            domain = []
        elif probes:
            cells = set()
            for q, col in probes:
                code = self.index.code(q).item()
                for near in (code, *(code ^ (1 << j) for j in range(8))):
                    hits = self.index.buckets.get((tab, col, near), ())
                    self.count["bucket_visits"] += len(hits)
                    cells.update(k[0] for k in hits)
            domain = [
                k
                for owner in cells
                for k in self.index.owners[owner]
                if self.store.visible[k]["table"] == tab
            ]
        else:
            domain = list(self.live[tab])
        self.count["visited"] += len(domain)
        self.count["reads"] += 1
        exclude = set(exclude)
        fresh_required = (
            len(prefix) + 1 == len(order)
            and self.iface.rules[r]["metadata"]["seminaive"]
            and not any(self.store.visible[k]["version"] >= wm for k in prefix)
        )
        domain = [
            k
            for k in domain
            if (k, self.store.visible[k]["version"]) not in exclude
            and (not fresh_required or self.store.visible[k]["version"] >= wm)
        ]
        # Canonical address order for deterministic ties. Cyclic paging gives unscored
        # candidates a chance on subsequent attempts; comparisons use neural vectors.
        if self.store.rng is None:
            domain.sort()
        else:
            # Keep the same evidence page in the paired renaming experiment.
            domain.sort(key=lambda k: (self.store.original[k[0]], k[1]))
        if len(domain) > cap:
            offset = (step * cap) % len(domain)
            domain = (domain[offset:] + domain[:offset])[:cap]
        domain = list(dict.fromkeys([*domain, *force]))
        if not domain:
            return [], torch.empty(0, WIDTH + 12)
        self.count["scored_ports"] += len(domain)
        idx = self.index
        bank = torch.stack([idx.keys[k].mean(0) for k in domain])
        dots = (
            torch.stack(
                [
                    torch.stack([idx.keys[k][col] for k in domain]) @ q
                    for q, col in probes
                ]
            )
            if probes
            else torch.zeros(1, len(domain))
        )
        extra = []
        for k in domain:
            row = self.store.visible[k]
            kind = self.store.types[k[0]][0]
            extra.append(
                [
                    len(prefix) / 8,
                    len(order) / 8,
                    float(row["version"] >= wm),
                    min(1, log1p(max(0, wm - row["version"])) / 8),
                    float(row["forwarded"]),
                    float(kind == "initial"),
                    float(kind == "repair"),
                    min(k[1], 64) / 64,
                    len(row["hashes"]) / 8,
                ]
            )
        x = torch.cat(
            [
                bank,
                dots.mean(0)[:, None],
                dots.amin(0)[:, None],
                dots.amax(0)[:, None],
                torch.tensor(extra),
            ],
            1,
        )
        return domain, x


class Policy:
    def __init__(self, program, root, model, persistent=False, max_owners=None):
        self.reader = Reader(program, root)
        self.model = model
        self.persistent = persistent
        self.max_owners = max_owners
        self.pool = OrderedDict()
        self.wait = defaultdict(OrderedDict)
        self.ready = defaultdict(OrderedDict)
        self.active = defaultdict(OrderedDict)
        self.last_rule = {}
        self.observer = None
        self.selection_observer = None
        self.pool_limit = POOL
        self.closed = OrderedDict()
        self.by_ref = defaultdict(set)
        self.count = Counter()

    def forget(self, key, why):
        self.pool.pop(key)
        r, seq = key
        t = self.next_table(r, len(seq))
        self.wait[t].pop(key, None)
        self.ready[r].pop(key, None)
        self.active[r].pop(key, None)
        for addr, _ in seq:
            self.by_ref[addr].discard(key)
            if not self.by_ref[addr]:
                del self.by_ref[addr]
        self.count[why] += 1

    def next_table(self, r, n):
        rd = self.reader
        return rd.tabs[rd.iface.roles[r][rd.order(r)[n]][0]]

    def save(self, r, seq, tried, run, priority):
        if not self.persistent or not seq:
            return
        rd = self.reader
        key = (r, tuple((a, rd.store.visible[a]["version"]) for a in seq))
        t = self.next_table(r, len(seq))
        old = self.closed.get(key)
        if old is not None and old[0] == rd.versions[t]:
            return
        if key not in self.pool:
            if len(self.pool) >= self.pool_limit:
                self.forget(next(iter(self.pool)), "evicted")
            self.pool[key] = Obligation(*key)
            if old is not None:
                self.pool[key].tried.update(self.closed.pop(key)[1])
            self.wait[t][key] = None
            for a, _ in key[1]:
                self.by_ref[a].add(key)
        ob = self.pool[key]
        if ob.generation != rd.versions[t]:
            ob.attempts = 0
        ob.tried.update(tried)
        ob.last = run
        ob.attempts += 1
        ob.priority = priority
        self.active[r][key] = None
        if ob.attempts >= 4:
            self.closed[key] = (rd.versions[t], ob.tried)
            if len(self.closed) > self.pool_limit:
                self.closed.popitem(last=False)
            self.forget(key, "closed_attempt_limit")
            return
        ob.generation = rd.versions[t]

    @torch.no_grad()
    def issue(self, f, explore=False):
        rd = self.reader
        for a in [*f["retired"], *(x for x, _ in f["updates"])]:
            addr = a["token"], a["op"]
            for key in tuple(self.by_ref.get(addr, ())):
                self.forget(key, "invalidated")
        changed = rd.advance(f)
        for t in changed:
            for key in self.wait.get(t, ()):
                self.count["event_notifications"] += 1
                self.ready[key[0]][key] = None
        packets = []
        frontier = set()
        spend = 0
        run = f["run"]
        emitted = set()
        sched = f["rules"]
        ranks = (
            self.model.activation(
                torch.tensor(
                    [
                        rd.rule_state(r, wm, run, self.last_rule.get(r, 0))
                        for r, wm in sched
                    ],
                    dtype=torch.float32,
                ).reshape(-1, 8)
            )
            .flatten()
            .tolist()
        )
        proactive = True
        for j in sorted(range(len(sched)), key=lambda j: -ranks[j]):
            r, wm = sched[j]
            order = rd.order(r)
            if not order:
                if wm == 0 or not rd.iface.rules[r]["metadata"]["seminaive"]:
                    if len(packets) < RUN_PACKETS:
                        packets.append(request(run, r, (), rd.store))
                continue
            if spend >= RUN_EXPANSIONS or len(packets) >= RUN_PACKETS:
                continue
            h0 = self.model.start(rd.meta(r))
            starts = []
            # Event queue is indexed by the missing table. Bounded fairness rotates
            # one record; no history or pool scan to discover dormant work.
            if self.persistent:
                queue = self.ready[r]
                keys = list(islice(queue, 6))
                if keys:
                    keys = [max(keys, key=lambda k: self.pool[k].priority)]
                self.count["event_wakes"] += len(keys)
                if not keys and proactive and self.active[r]:
                    options = list(islice(self.active[r], 4))
                    k = max(options, key=lambda k: self.pool[k].priority)
                    self.active[r].move_to_end(k)
                    keys.append(k)
                    proactive = False
                    self.count["proactive_wakes"] += 1
                if run % 7 == 0 and self.pool:
                    k = next(iter(self.pool))
                    self.pool.move_to_end(k)
                    if k[0] == r and k not in keys:
                        keys.append(k)
                        self.count["fair_wakes"] += 1
                for key in keys:
                    queue.pop(key, None)
                    ob = self.pool[key]
                    if ob.last == run:
                        continue
                    if (
                        ob.attempts >= 4
                        and ob.generation
                        == rd.versions[self.next_table(r, len(key[1]))]
                    ):
                        continue
                    seq = tuple(a for a, _ in key[1])
                    h = h0
                    score = 0.0
                    for j, addr in enumerate(seq):
                        _, x = rd.read(r, seq[:j], wm, 0, cap=0, force=[addr])
                        s, h = self.model(h, x)
                        score += s.item()
                    starts.append((seq, h, score, ob))
                    self.count["resumed"] += 1
            starts.append(((), h0, 0.0, None))
            for prefix, h, score, ob in starts:
                work = [(prefix, h, score)]
                while work and spend < RUN_EXPANSIONS and len(packets) < RUN_PACKETS:
                    next_work = []
                    for seq, h, score in work:
                        if spend >= RUN_EXPANSIONS:
                            break
                        spend += 1
                        if seq:
                            frontier.update(k[0] for k in seq)
                        live_key = (
                            r,
                            tuple((a, rd.store.visible[a]["version"]) for a in seq),
                        )
                        closed = self.closed.get(live_key)
                        if (
                            closed
                            and closed[0] == rd.versions[self.next_table(r, len(seq))]
                        ):
                            continue
                        saved = self.pool.get(live_key)
                        skip = saved.tried if saved else closed[1] if closed else ()
                        domain, x = rd.read(
                            r, seq, wm, saved.attempts if saved else 0, skip
                        )
                        frontier.update(k[0] for k in domain)
                        if (
                            self.max_owners
                            and len({k[0] for k in seq}) >= self.max_owners
                        ):
                            ids = [
                                i
                                for i, k in enumerate(domain)
                                if k[0] in {a[0] for a in seq}
                            ]
                            domain = [domain[i] for i in ids]
                            x = x[ids]
                        if self.observer is not None:
                            self.observer(r, seq, domain)
                        if not domain:
                            self.save(
                                r, seq, (), run, float(self.model.retry(h).item())
                            )
                            continue
                        ss, zz = self.model(h, x)
                        rank = ss if not explore else ss + torch.rand_like(ss) * 1.5
                        ids = rank.argsort(descending=True, stable=True)[
                            :FANOUT
                        ].tolist()
                        if seq:
                            self.save(
                                r, seq, (), run, float(self.model.retry(h).item())
                            )
                        if self.selection_observer is not None:
                            self.selection_observer(r, seq, [domain[i] for i in ids], "fanout")
                        for i in ids:
                            path = seq + (domain[i],)
                            next_work.append((path, zz[i], score + ss[i].item(), seq))
                    next_work.sort(key=lambda v: -v[2])
                    work = []
                    for path, z, s, parent in next_work[:BEAM]:
                        if len(packets) >= RUN_PACKETS:
                            break
                        if self.selection_observer is not None:
                            self.selection_observer(r, parent, [path[-1]], "beam")
                        if parent and self.persistent:
                            key = (
                                r,
                                tuple(
                                    (a, rd.store.visible[a]["version"]) for a in parent
                                ),
                            )
                            attempt = (path[-1], rd.store.visible[path[-1]]["version"])
                            if key in self.pool:
                                self.pool[key].tried.add(attempt)
                            elif key in self.closed:
                                self.closed[key][1].add(attempt)
                        if len(path) < len(order):
                            work.append((path, z, s))
                            continue
                        addrs = rd.addresses(r, path)
                        sig = (r, tuple(addrs))
                        if sig not in emitted:
                            emitted.add(sig)
                            packets.append(request(run, r, addrs, rd.store))
                if spend >= RUN_EXPANSIONS or len(packets) >= RUN_PACKETS:
                    break
        for q in packets:
            self.last_rule[q["rule"]] = run
        self.count["bounded_runs"] += int(
            spend >= RUN_EXPANSIONS or len(packets) >= RUN_PACKETS
        )
        self.count["expansions"] += spend
        self.last_frontier = len(frontier)
        return packets
