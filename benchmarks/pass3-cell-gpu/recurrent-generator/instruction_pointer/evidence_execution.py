"""Select a Recipe region on publication, before ordinary B starts parent search."""

from collections import Counter, defaultdict
from dataclasses import dataclass, field

import numpy as np
import torch

from cell_transaction import STATUS
from entry_model import scores
from evidence_regions import HORIZON, INPUT, OUTPUT, PARTNER
from higher_replacement import send
from recursive_train import read
from ripsat_layout import signatures
from structure_runtime import StructureEntries, live


@dataclass
class Region:
    pid: int
    source: int
    entry: int
    boundary: dict
    tokens: dict = field(default_factory=dict)  # missing = waiting; None = failed
    returns: dict = field(default_factory=dict)
    partner_reads: int = 0
    independent: int = 1
    issued: int = 0
    horizontal: int = 0
    vertical: int = 0
    later: int = 0


class EvidenceEntries(StructureEntries):
    def __init__(self, program, store, weights, graph, contracts, rules):
        super().__init__(program, store, weights, graph, contracts, rules)
        sigs = signatures(program)
        ids = defaultdict(list)
        for r, s in enumerate(sigs):
            ids[s].append(r)
        self.by_source = defaultdict(list)
        self.regions = {}
        self.interface = {}
        for pid, (source, recorded) in enumerate(read(store / "evidence-book.json")["regions"]):
            kind, key = source
            if kind == "rule" and len(ids[key]) != 1:
                continue
            if any(len(ids[s]) != 1 for s, _ in recorded):
                continue
            source = ("generated", ids[key][0]) if kind == "rule" else tuple(source)
            plan = tuple((ids[s][0], tuple(map(tuple, w))) for s, w in recorded)
            ports = set()
            external_types = {}
            for i, (r, wires) in enumerate(plan):
                if len(wires) != len(self.plans[r, 0].remaining) + 1:
                    raise ValueError("incompatible Recipe inputs")
                for role, (owner, pc) in enumerate(wires):
                    if owner >= i or owner < PARTNER or pc < 0:
                        raise ValueError("invalid evidence wiring")
                    required = rules[r]["inputs"][role]["table"]
                    if owner >= 0:
                        produced = rules[plan[owner][0]]["outputs"].get(str(pc))
                        if produced is None or produced["table"] != required:
                            raise ValueError("incompatible internal named output")
                    elif external_types.setdefault((owner, pc), required) != required:
                        raise ValueError("inconsistent external port type")
                    elif kind == "rule" and owner in (INPUT, OUTPUT):
                        src_rule = rules[source[1]]
                        site = src_rule["inputs"][pc] if owner == INPUT else src_rule["outputs"][str(pc)]
                        if site["table"] != required:
                            raise ValueError("source role does not supply the required table")
                    elif (
                        kind == "initial"
                        and owner == OUTPUT
                        and program["recipe"]["tables"][required]["name"] != key
                    ):
                        raise ValueError("incorrect initial evidence table")
                    if owner < 0:
                        ports.add((owner, pc))
            self.regions[pid] = plan
            self.interface[pid] = ports
            self.by_source[source].append(pid)
        self.descriptors = {}
        self.seen_sources = set()
        self.active = []
        self.activations = []

    def start(self, rd, pub, txn, rules, stats):
        super().start(rd, pub, txn, rules, stats)
        self.sources.update(source for kind, source in self.by_source if kind == "generated")
        self.births = defaultdict(dict)
        for t, pc, table, v, *_ in pub[0]:
            t = int(t)
            if t not in self.seen_sources and rd.store.types[t] in self.by_source:
                self.births[t][int(pc)] = (t, int(pc), int(v))
        self.seen_sources.update(self.births)
        self.just_published = set(map(int, pub[3][:, 0]))
        self.prefixes = defaultdict(lambda: defaultdict(set))

    def descriptor(self, mem, pid):
        if pid not in self.descriptors:
            plan = self.regions[pid]
            code = np.mean([self.code(mem, r, 0) for r, _ in plan], axis=0)
            for r, wires in plan:
                for j, (owner, pc) in enumerate(wires):
                    code[(j + 2 * (owner + 3)) % len(code)] += np.log1p(pc + 1) / (8 * len(plan))
            self.descriptors[pid] = code
        return self.descriptors[pid]

    def resume_programs(self, mem):
        super().resume_programs(mem)
        self.mem = mem
        waiting, self.active = self.active, []
        for region in waiting:
            self.advance_region(region, mem)
        for token, outputs in self.births.items():
            pids = self.by_source[mem.rd.store.types[token]]
            pc = min(outputs)
            table = mem.rd.store.visible[token, pc]["table"]
            bank = mem.bank(table)
            pos = bank.positions[token, pc]
            codes = [self.code(mem, self.regions[pids[0]][0][0], 0), *(self.descriptor(mem, i) for i in pids)]
            logits = scores(
                self.model, torch.from_numpy(bank.vec[pos : pos + 1]), torch.from_numpy(np.stack(codes))
            )
            k = int(logits.argmax())
            if self.exploration is not None and self.exploration.random() < 0.20:
                k = int(self.exploration.integers(len(codes)))
            self.count["evidence_option_scores"] += len(codes)
            self.action_counts["EvidenceActivate" if k else "EvidencePass"] += 1
            self.action_runs.add(self.txn.run)
            if not k:
                continue
            pid = pids[k - 1]
            boundary = {}
            inputs = self.owners.get(token, ())
            for owner, op in self.interface[pid]:
                if owner == OUTPUT:
                    boundary[owner, op] = outputs.get(op)
                elif owner == INPUT:
                    boundary[owner, op] = tuple(map(int, inputs[op][:3])) if op < len(inputs) else None
            region = Region(pid, token, self.txn.run, boundary)
            self.activations.append(region)
            if (PARTNER, 0) in self.interface[pid]:
                self.bind_partner(region, mem)
            self.advance_region(region, mem)

    def bind_partner(self, region, mem):
        r, wires = next((r, w) for r, w in self.regions[region.pid] if (PARTNER, 0) in w)
        target = wires.index((PARTNER, 0))
        known = {j: region.boundary.get(w) for j, w in enumerate(wires) if j != target}
        if r not in self.rules or not all(live(mem.rd.store, p, mem.roles[r][j]) for j, p in known.items()):
            return
        self.action_counts["EvidenceBind"] += 1
        region.partner_reads += 1
        layout = tuple((-1, j) for j in range(len(wires)))
        other = self.bind(r, layout, target, known)
        if other is not None:
            region.boundary[PARTNER, 0] = tuple(map(int, other))
            region.independent += 1

    def advance_region(self, region, mem):
        plan = self.regions[region.pid]
        run = self.txn.run
        if run - region.entry > HORIZON:
            self.count["evidence_expired_steps"] += len(plan) - len(region.tokens)
            return
        for step, (r, wires) in enumerate(plan):
            if step in region.tokens:
                continue
            for w in wires:
                owner, pc = w
                tok = region.tokens.get(owner)
                if tok in self.just_published and w not in region.returns:
                    row = mem.rd.store.visible.get((tok, pc))
                    region.returns[w] = None if row is None else (tok, pc, int(row["version"]))
            if any(i >= 0 and i in region.tokens and region.tokens[i] is None for i, _ in wires):
                region.tokens[step] = None
                self.count["evidence_blocked_descendants"] += 1
                continue
            if r not in self.rules or any(i >= 0 and (i, pc) not in region.returns for i, pc in wires):
                continue
            refs = tuple(region.returns[w] if w[0] >= 0 else region.boundary.get(w) for w in wires)
            region.tokens[step] = None
            if not all(live(mem.rd.store, ref, tab) for ref, tab in zip(refs, mem.roles[r], strict=True)):
                self.count["evidence_unavailable"] += 1
                continue
            if refs in self.done[r] or (
                mem.rd.iface.rules[r]["metadata"]["seminaive"] and all(p[2] < self.rules[r] for p in refs)
            ):
                self.count["evidence_done_or_old"] += 1
                continue
            reply = send(self.txn, r, np.asarray([refs], np.int64))[0]
            region.issued += 1
            self.count["evidence_reply_" + STATUS[int(reply[1])]] += 1
            if reply[1] != 0:
                continue
            tok = int(reply[0])
            vertical = any(i >= 0 for i, _ in wires)
            region.vertical += vertical
            region.horizontal += not vertical
            region.later += run > region.entry
            region.tokens[step] = tok
            self.suffix_tokens[tok] = ("Evidence", 1)
            self.publish_next.append((tok, r, 1, tuple(p[0] for p in refs)))
            self.done[r].add(refs)
            self.covered_rules[r] = self.done[r]
            self.covered_indices = {k: v for k, v in self.covered_indices.items() if k[0] != r}
            coords = tuple(mem.bank(t).positions[p[:2]] for t, p in zip(mem.roles[r], refs, strict=True))
            self.struct_positions[r][coords] = "evidence"
            self.suffix_positions[r].add(coords)
            if len(coords) == 2:
                for j in (0, 1):
                    self.prefixes[r, j][coords[j]].add(coords[1 - j])
        if len(region.tokens) < len(plan):
            self.active.append(region)

    def remaining_binary_roots(self, mem, r, order, ix):
        known = self.prefixes.get((r, order[0]))
        if not known:
            return ix
        subset = np.asarray([int(i) for i in ix if i in known], dtype=np.int64)
        if not len(subset):
            return ix
        post, starts, counts = mem.window(r, order[:1], order[1], subset[:, None])
        skipped = set()
        for i, lo, n in zip(subset, starts, counts, strict=True):
            if n and n <= len(known[i]):
                candidates = range(lo, lo + n) if post is None else post[lo : lo + n]
                self.count["evidence_certificate_position_checks"] += int(n)
                if all(k in known[i] for k in candidates):
                    skipped.add(i)
                    self.count["evidence_certified_leaf_scores_skipped"] += int(n)
        self.count["evidence_binary_root_scores_skipped"] += len(skipped)
        return ix[[i not in skipped for i in ix]] if skipped else ix

    def structure_report(self, origins):
        credit = Counter()
        for t, n in origins:
            credit[t] += int(n)
        report = super().structure_report(origins)
        for reg in self.activations:
            tokens = [t for t in reg.tokens.values() if t is not None]
            report.append(
                {
                    "mode": "Evidence",
                    "pid": reg.pid,
                    "source": reg.source,
                    "entry": reg.entry,
                    "tokens": tokens,
                    "operations": sum(credit[t] for t in tokens),
                    "issued": reg.issued,
                    "bindings": reg.independent,
                    "additional_attempts": reg.partner_reads,
                    "horizontal": reg.horizontal,
                    "vertical": reg.vertical,
                    "later": reg.later,
                }
            )
        return report
