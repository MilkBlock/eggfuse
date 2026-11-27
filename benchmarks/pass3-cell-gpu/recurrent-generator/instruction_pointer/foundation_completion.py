"""Two factorizations of the same complete primitive Cell; no semantic host filtering."""

from collections import defaultdict
from dataclasses import dataclass
from math import log

import numpy as np
import torch

from address_scores import mlp
from discrete_draft import Cell
from foundation_memory import AssociationMemory


@dataclass
class Choice:
    q: torch.Tensor
    keys: torch.Tensor
    bias: torch.Tensor
    kind: int
    entry: bool = False

    def logp(self, net):
        k = self.keys
        q = self.q.expand_as(k)
        zero = torch.zeros_like(k)
        score = net.gate if self.kind == 0 else net.scorer
        logits = (
            mlp(score, q, zero, k, self.kind) - mlp(score, q, k, zero, self.kind)
        ) * 0.5
        return (logits + self.bias).log_softmax(0)


class Decision:
    """The same choice law is used for free draws and for target log likelihood."""

    def __init__(self, net=None, rng=None, stats=None):
        self.net, self.rng, self.stats = net, rng, stats
        self.terms = []

    def pick(self, labels, q, keys, kind, target=None, bias=None):
        if len(labels) == 1:
            if target is not None and labels[0] != target:
                raise ValueError("target outside singleton domain")
            return labels[0]
        if not len(labels):
            raise ValueError("empty choice domain")
        c = Choice(q, keys, keys.new_zeros(len(labels)) if bias is None else bias, kind)
        if target is not None:
            self.terms.append((c, labels.index(target)))
            return target
        self.stats["scored_options"] += len(labels)
        self.stats["categorical_reads"] += 1
        lp = c.logp(self.net)
        i = torch.searchsorted(
            lp.exp().cumsum(0), lp.new_tensor(self.rng.random())
        ).clamp_max(len(labels) - 1)
        return labels[int(i)]


class Completion:
    def __init__(self, model, mode, device="mps", width=32, relation=True):
        self.net = model.local.base.to(device)
        self.mem = AssociationMemory(model.mapping, device, width)
        self.mode, self.device, self.relation = mode, device, relation
        self.schedule = {}
        self.schemas = []
        self.wiring = []

    def publish(self, m, prog, frame, stats):
        self.mem.publish(m, frame, stats)
        rules = prog["recipe"]["rules"]
        for rid in range(len(self.schemas), len(rules)):
            rule = rules[rid]
            fields = [
                [c.get("slot") for c in row["columns"]]
                for row in rule["interface"]["rows"]
            ]
            roles = m.enc.nodes[m.enc.cat.inputs["generated", rid]].to(self.device)
            if len(fields) != len(m.roles[rid]):
                raise ValueError("Recipe role layout mismatch")
            self.schemas.append((m.roles[rid], roles))
            self.wiring.append(
                {
                    (i, j): [
                        (a, b)
                        for a, s in enumerate(src)
                        for b, v in enumerate(dst)
                        if s is not None and s == v
                    ]
                    for i, src in enumerate(fields)
                    for j, dst in enumerate(fields)
                    if i != j
                }
            )
        self.ids = [r for r, h in m.ids if not h]
        if not self.ids:
            return
        schedule = tuple(self.ids)
        if schedule not in self.schedule:
            options = defaultdict(list)
            for r in self.ids:
                for j, t in enumerate(self.schemas[r][0]):
                    options[t].append((r, j))
            self.schedule[schedule] = options
        self.opts = self.schedule[schedule]
        self.ctx = m.context().to(self.device)
        keys = torch.stack([m.graph((r, False)) for r in self.ids]).to(self.device)
        self.rpos = {r: i for i, r in enumerate(self.ids)}
        counts = np.zeros((len(self.ids), 4), np.float32)
        for i, r in enumerate(self.ids):
            for j, t in enumerate(self.schemas[r][0][:4]):
                counts[i, j] = np.log1p(self.mem.live_count.get(t, 0)) / 8
        keys[:, 12:16] += torch.from_numpy(counts).to(self.device)
        self.rkeys = keys
        self.role_keys = {}
        self.coarse = {}

    def page_options(self, table):
        if table not in self.coarse:
            pgs = self.mem.groups(table)
            if pgs:
                keys = torch.stack([self.mem.pages[i].mean for i in pgs])
                bias = keys.new_tensor([log(len(self.mem.pages[i].refs)) for i in pgs])
            else:
                keys = self.ctx.new_empty((0, self.ctx.numel()))
                bias = self.ctx.new_empty(0)
            self.coarse[table] = (pgs, keys, bias)
        return self.coarse[table]

    def entry(self, dec, desired=None):
        # A learned choice between a Recipe start (-1) and every physical evidence page.
        pgs, keys, bias = self.page_options(None)
        if not pgs:
            return -1
        result = dec.pick(
            [-1] + pgs,
            self.ctx,
            torch.cat((self.ctx.new_zeros(1, 32), keys)),
            0,
            desired,
            torch.cat((bias.new_zeros(1), bias - bias.logsumexp(0))),
        )
        if desired is not None:
            dec.terms[-1][0].entry = True
        return result

    def finish(
        self, dec, *, goal=None, route=None, stats=None, hint=None, fixed_rule=None
    ):
        # route=-1 starts from a Recipe, nonnegative route is a target role in teacher forcing.
        # hint=(ref,role not provided): only used by the separate offline diagnostic.
        start_role = None
        target_rule = goal.rule if goal is not None else None
        pg = -1
        if hint is not None:
            pg = self.mem.lookup(hint)[0]
        elif self.mode == "evidence":
            desired = None
            if goal is not None:
                desired = -1 if route == -1 else self.mem.lookup(goal.refs[route])[0]
            pg = self.entry(dec, desired)
        self.last_anchor = None
        self.last_role = None
        assigned = {}
        if pg == -1:
            rid = (
                dec.pick(self.ids, self.ctx, self.rkeys, 0, target_rule)
                if fixed_rule is None
                else fixed_rule
            )
            if stats is not None:
                stats["recipe_starts"] += 1
        else:
            p = self.mem.pages[pg]
            anchor = (
                hint
                if hint is not None
                else dec.pick(
                    p.refs,
                    self.ctx,
                    p.keys,
                    1,
                    goal.refs[route] if goal is not None else None,
                )
            )
            self.last_anchor = anchor
            if stats is not None:
                stats["evidence_starts"] += 1
            opts = self.opts.get(p.table, ())
            if not opts:
                if stats is not None:
                    stats["no_static_role"] += 1
                return None, None
            if p.table not in self.role_keys:
                self.role_keys[p.table] = torch.stack(
                    [
                        (self.rkeys[self.rpos[r]] + self.schemas[r][1][j]).tanh()
                        for r, j in opts
                    ]
                )
            aq = (self.ctx + self.mem.lookup(anchor)[1]).tanh()
            rid, start_role = dec.pick(
                opts,
                aq,
                self.role_keys[p.table],
                0,
                (target_rule, route) if goal is not None else None,
            )
            self.last_role = start_role
            assigned[start_role] = anchor
        tabs, roles = self.schemas[rid]
        for j, t in enumerate(tabs):
            if j in assigned:
                continue
            pgs, keys, bias = self.page_options(t)
            if not pgs:
                if stats is not None:
                    stats["empty_domain"] += 1
                return rid, None
            bound = [(i, self.mem.lookup(ref)) for i, ref in assigned.items()]
            q = self.ctx + self.rkeys[self.rpos[rid]] + roles[j]
            if bound:
                q = q + torch.stack([b[1] for _, b in bound]).mean(0)
            q = q.tanh()
            target = goal.refs[j] if goal is not None else None
            pg = dec.pick(
                pgs,
                q,
                keys,
                1,
                self.mem.lookup(target)[0] if target is not None else None,
                bias,
            )
            page = self.mem.pages[pg]
            rel = q.new_zeros(len(page.refs))
            # Static Recipe wires choose fields. All dot products for a candidate
            # use the SAME named row. No host data-dependent intersection.
            if self.relation:
                for i, (_, _, fields) in bound:
                    for a, b in self.wiring[rid][i, j]:
                        rel += 6 * (page.fields[:, b] @ fields[a])
            assigned[j] = dec.pick(page.refs, q, page.keys, 1, target, rel)
            if stats is not None:
                stats["row_positions"] += len(page.refs)
        return rid, Cell(rid, tuple(assigned[j] for j in range(len(tabs))))

    def paths(self, goal):
        routes = [-1] + (list(range(len(goal.refs))) if self.mode == "evidence" else [])
        out = []
        for route in routes:
            d = Decision()
            _, cell = self.finish(d, goal=goal, route=route)
            assert cell == goal
            out.append(d.terms)
        return out

    def generate(self, m, slots, rng, stats):
        draws = []
        self.events = []
        for _ in range(slots):
            draws.append(self.finish(Decision(self.net, rng, stats), stats=stats))
            self.events.append(
                {"anchor": self.last_anchor, "anchor_role": self.last_role}
            )
        return tuple(map(list, zip(*draws)))
