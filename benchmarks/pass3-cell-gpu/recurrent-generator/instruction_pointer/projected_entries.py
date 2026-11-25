"""Instantiate a B-selected layout from one published producer or its general root."""
from time import perf_counter

import numpy as np

from entry_rollout import Entries
from higher_replacement import send
from multi_entry import link_entries, resolve


class ProjectedEntries(Entries):
    def __init__(self, program, store, weights, graph, contracts, receipt_rules, preferred=()):
        super().__init__(program, store, weights, graph)
        options = link_entries(program, self.manifest, contracts, receipt_rules)
        self.routes = {}
        self.owners = {}
        self.cursor = 0
        self.events = []
        self.completions = []
        self.started = {}
        self.preferred = tuple(preferred)
        if any(i not in range(len(contracts["entries"])) for i in preferred):
            raise ValueError("unknown entry contract ID")
        self.options = options

    def start(self, rd, pub, txn, rules, stats):
        if self.started:
            for uid, _, tokens, _, step in self.waiting:
                if step == len(self.cat.units[uid]) and tokens[0] in self.started:
                    self.completions.append((txn.run, self.started[tokens[0]], uid, list(tokens)))
        super().start(rd, pub, txn, rules, stats)
        if self.options is not None:
            for key, alternatives in self.options.items():
                r, j, src, pc = key
                for uid in self.family.menu.get(r, ()):
                    # Static lowering of an explicitly chosen body. Prefer its
                    # witnessed entry; no online value or candidate is inspected.
                    self.routes[uid, j, src, pc] = sorted(alternatives, key=lambda pair: (
                        pair[1]["observed_complete_bodies"].get(str(uid), 0),
                        pair[1]["verified_roots"], -pair[0]), reverse=True)
            self.root_rules = {r for r, _, _, _ in self.options}
            self.sources = {src for _, _, src, _ in self.routes}
            self.options = None
        # Store slices of the existing accepted transaction buffers. A ticket
        # from this Run can first supply input provenance at the next publication.
        while self.cursor < len(txn.accepted):
            run, ops, widths, refs = txn.accepted[self.cursor]
            if run >= txn.run:
                break
            self.cursor += 1
            at = 0
            for (token, source), width in zip(ops, widths, strict=True):
                if source in self.sources:
                    self.owners[int(token)] = refs[at:at + width]
                    stats["entry_provenance_slices"] += 1
                at += width

    def route(self, key, contract_id=None):
        alternatives = self.routes.get(key, ())
        if contract_id is None:
            for cid in self.preferred:
                for pair in alternatives:
                    if pair[0] == cid:
                        return pair
            return alternatives[0] if alternatives else None
        return next((pair for pair in alternatives if pair[0] == contract_id), None)

    def project_entries(self, r, j, mem, txn):
        if not self.choice or j < 0 or r not in self.root_rules:
            return
        start = perf_counter()
        bank = mem.bank(mem.roles[r][j])
        store = mem.rd.store
        rows = {}
        for pos, uid in self.choice.items():
            token, pc = bank.ports[pos]
            kind, source = store.types[token]
            if kind != "generated":
                continue
            self.count["entry_dispatch_lookups"] += 1
            route = self.route((uid, j, source, pc))
            if route is None:
                continue
            cid, contract = route
            self.count["entry_projected_operands"] += len(contract["reads"])
            refs = resolve(contract["reads"], token, self.owners.get(token, ()), store.visible)
            if refs is None:
                self.count["entry_unavailable"] += 1
            elif (mem.rd.iface.rules[r]["metadata"]["seminaive"]
                  and all(v < self.rules[r] for _, _, v in refs)):
                self.count["entry_old_only"] += 1
            elif refs not in self.done[r]:
                rows.setdefault(refs, (uid, cid, token))
        keys = list(rows)
        for at in range(0, len(keys), txn.capacity):
            batch = keys[at:at + txn.capacity]
            replies = send(txn, r, np.asarray(batch, np.int64))
            for refs, response in zip(batch, replies, strict=True):
                uid, cid, owner = rows[refs]
                status = int(response[1])
                self.count["entry_probes"] += 1
                self.events.append((txn.run, cid, uid, owner, int(response[0]), status))
                if status != 0:
                    continue
                self.count["entry_accepted"] += 1
                self.count["root_other_bindings_replaced"] += len(refs) - 1
                self.started[int(response[0])] = cid
                self.begin(uid, refs, int(response[0]), txn)
                self.done[r].add(refs)
                self.covered_rules[r] = self.done[r]
        if rows:
            for key in list(self.covered_indices):
                if key[0] == r:
                    del self.covered_indices[key]
        self.count["entry_dispatch_seconds"] += perf_counter() - start
