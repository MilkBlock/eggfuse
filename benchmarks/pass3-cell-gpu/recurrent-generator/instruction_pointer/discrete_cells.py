"""Shared structural mark decoder. Named addressing reads two pivots per tree level."""

import json
import subprocess
from collections import defaultdict
from pathlib import Path
from time import perf_counter

import torch
from torch import nn

from discrete_draft import Cell, Local
from latent_cell_flow import WIDTH, ZERO, Frozen, Published
from latent_egg_higher import bake
from recursive_train import binary, read
from ripsat_policy import CellScorer, GraphBank
from rule_read import load_actor


def load_enc(program, actor_path):
    scorer = CellScorer(WIDTH).eval()
    scorer.load_state_dict(
        torch.load("run-recall/parameterized-deep-ripsat/event-gnn.pt", weights_only=True)["model"]
    )
    return Frozen(program, load_actor(actor_path, True).eval(), scorer), scorer


def from_q(q):
    return Cell(
        q["rule"], tuple((p["address"]["token"], p["address"]["op"], p["version"]) for p in q["parents"])
    )


class Memory:
    def __init__(self, enc, contract, menu, scorer):
        self.enc = enc
        self.pub = Published(enc)
        self.roles = [tuple(a["table"] for a in r["inputs"]) for r in contract["rules"]]
        self.output_tables = [
            {int(pc): site["table"] for pc, site in r["outputs"].items()} for r in contract["rules"]
        ]
        self.menu = menu
        self.codes = (
            dict(zip(menu, GraphBank(list(menu.values()), enc.cat, enc.nodes).encode(scorer))) if menu else {}
        )
        self.rows = defaultdict(list)
        self.index = {}
        self.options = {}
        self.last = None
        self.receipt = ZERO.clone()

    def update(self, f):
        self.pub.change(f, True)
        for a, r in f["updates"]:
            key = a["token"], a["op"]
            tab = r["table"]
            if (tab, key) not in self.index:
                self.index[tab, key] = len(self.rows[tab])
                self.rows[tab].append(key)
        self.state = (self.pub.total.float() / 16).asinh().tanh() + 0.1 * self.receipt
        self.event = ZERO
        if f["updates"]:
            a = f["updates"][-1][0]
            self.last = (a["token"], a["op"])
        if self.last in self.pub.live:
            self.event = self.pub.live[self.last][1]
        # Only native scheduling determines the legal static template vocabulary.
        rules = tuple(k for k, _ in f["rules"])
        if rules not in self.options:
            ids = [(r, h) for r in rules for h in ((False, True) if r in self.menu else (False,))]
            self.options[rules] = (ids, {v: i for i, v in enumerate(ids)})
        self.ids, self.ids_index = self.options[rules]

    def graph(self, key):
        r, h = key
        return self.codes[r] if h else self.enc.graphs[r]

    def key(self, ref):
        if ref not in self.pub.live:
            return ZERO
        return self.pub.live[ref][1]

    def compatible(self, source, port, consumer, slot):
        return self.output_tables[source.rule].get(port) == self.roles[consumer.rule][slot]

    def local_code(self, c, pc):
        node = self.enc.cat.outputs.get((("generated", c.rule), pc))
        return (self.graph((c.rule, c.higher)) + (self.enc.nodes[node] if node is not None else ZERO)).tanh()

    def embed(self, c):
        if c is None:
            return ZERO
        q = dict(
            rule=c.rule,
            parents=[
                dict(address=dict(token=a[0], op=a[1]), version=a[2])
                for a in c.refs
                if not isinstance(a, Local)
            ],
        )
        enc = self.enc.token(q, self.pub.live)
        local = ZERO
        for i, ref in enumerate(c.refs):
            if isinstance(ref, Local):
                from actor import rotate

                local = (
                    local
                    + rotate(
                        self.enc.nodes[self.enc.cat.inputs["generated", c.rule][i]][None],
                        torch.tensor([ref.port]),
                    )[0]
                )
        return (self.graph((c.rule, c.higher)) + enc[WIDTH:] + local).tanh()

    def context(self):
        return (self.state + self.event).tanh()


class Marks(nn.Module):
    def __init__(self):
        super().__init__()
        self.choice = nn.Sequential(nn.Linear(WIDTH * 3 + 3, 48), nn.Tanh(), nn.Linear(48, 1))

    def branch(self, q, left, right, mode):
        return torch.cat(
            (q, left, right, torch.tensor([float(mode == 0), float(mode == 1), float(mode == 2)]))
        )

    def draw(
        self, m, rng, stats, hint=None, target=None, records=None, prefix=(), weight=1.0, oracle_key=None
    ):
        train = records is not None
        stats["mark_draws"] += 1

        def choose(x, answer):
            if train:
                records.append((x, answer, weight))
                return answer
            stats["address_forward_calls"] += 1
            return int(rng.random() < self.choice(x).sigmoid().item())

        def route(keys, key_fn, wanted, mode, q):
            if not keys:
                return None
            lo = 0
            hi = len(keys)
            while hi - lo > 1:
                mid = (lo + hi) // 2
                a = key_fn(keys[(lo + mid - 1) // 2])
                b = key_fn(keys[(mid + hi - 1) // 2])
                stats["template_probe" if mode == 0 else "port_probe"] += 2
                right = choose(self.branch(q, a, b, mode), int(wanted >= mid) if train else 0)
                if right:
                    lo = mid
                else:
                    hi = mid
            return keys[lo]

        ctx = m.context()
        if hint:
            ctx = (ctx + m.embed(hint)).tanh()
        tid = (target.rule, target.higher) if train else None
        if train and tid not in m.ids_index:
            return None
        tick = perf_counter()
        k = oracle_key if oracle_key is not None else route(m.ids, m.graph, m.ids_index.get(tid, 0), 0, ctx)
        stats["template_address_seconds"] += perf_counter() - tick
        if k is None:
            return None
        stats["template_probe"] += 1
        r, high = k
        q = (ctx + m.graph(k)).tanh()
        refs = []
        for i, tab in enumerate(m.roles[r]):
            tick = perf_counter()
            slot = m.enc.nodes[m.enc.cat.inputs["generated", r][i]]
            key = (q + slot).tanh()
            wanted = target.refs[i] if train else None
            locals_ = [
                (Local(v.uid, pc), m.local_code(v.cell, pc))
                for v in prefix
                for pc, t in m.output_tables[v.cell.rule].items()
                if t == tab
            ]
            stats["draft_local_ports_inspected"] += sum(len(m.output_tables[v.cell.rule]) for v in prefix)
            if locals_ and choose(self.branch(key, ZERO, locals_[0][1], 2), int(isinstance(wanted, Local))):
                index = next((j for j, (loc, _) in enumerate(locals_) if loc == wanted), 0) if train else 0
                loc, vec = route(locals_, lambda pair: pair[1], index, 1, key)
                refs.append(loc)
                q = m.enc.actor.next_read((vec + slot)[None], q[None])[0]
                stats["port_address_seconds"] += perf_counter() - tick
                continue
            if isinstance(wanted, Local):
                return None
            dest = wanted[:2] if train else None
            copy = None
            if hint and i < len(hint.refs) and not isinstance(hint.refs[i], Local):
                a = hint.refs[i][:2]
                if (tab, a) in m.index:
                    copy = a
            if copy is None and (tab, m.last) in m.index:
                copy = m.last
            if copy is not None:
                stats["port_probe"] += 1
                if not choose(self.branch(key, m.key(copy), ZERO, 2), int(dest != copy)):
                    picked = copy
                else:
                    picked = None
            else:
                picked = None
            if picked is None:
                if train and (tab, dest) not in m.index:
                    return None
                picked = route(m.rows[tab], m.key, m.index.get((tab, dest), 0), 1, key)
            stats["port_probe"] += 1
            if picked not in m.pub.live:
                return None
            row, vec = m.pub.live[picked]
            if row["table"] != tab:
                return None
            refs.append((*picked, row["version"]))
            q = m.enc.actor.next_read((vec + slot)[None], q[None])[0]
            stats["port_address_seconds"] += perf_counter() - tick
        return Cell(r, tuple(refs), high)


def setup(root, d, actor, fixture_layout=None, allow_high=False):
    prog = read(d / "program.json")
    enc, scorer = load_enc(prog, actor)
    contract = json.loads(subprocess.check_output([binary(root), "receipt-contract", d / "program.json"]))
    if fixture_layout:
        menu = {fixture_layout[0][0]: fixture_layout}
    elif allow_high:
        excluded = set(read(Path("run-recall/parameterized-deep-ripsat/catalog.json"))["structural_keys"])
        menu = bake(contract, enc, excluded)
    else:
        menu = {}
    return Memory(enc, contract, menu, scorer)
