"""Execute a single B choice over parameterized pairs of Cell interfaces."""

from collections import Counter, defaultdict
from dataclasses import dataclass

import numpy as np
import torch

from cell_stream import CellStream
from cell_transaction import STATUS
from higher_replacement import send
from recursive_ripsat import OpenEntries
from recursive_train import read
from structure_recipe import fanout, link


class PointerEntries(OpenEntries):
    def open_partner(self, r, j, pos, src, target, recent, mem, mode):
        if mode != "Compose":
            return super().open_partner(r, j, pos, src, target, recent, mem, mode)
        role, table = target
        bank = mem.bank(table)
        watermark = self.rules[r] if mem.rd.iface.rules[r]["metadata"]["seminaive"] else -1
        self.count["open_interface_probes"] += len(recent)
        eligible = [ref for ref in recent if ref[0] != src[0] and max(ref[2], src[2]) >= watermark]
        if not eligible:
            self.count["no_watermark_partner"] += 1
            return None
        order = (j, role)
        key = r, order
        if key not in self.pointers:
            ptr = CellStream(
                mem.rd,
                self.parent_model,
                r,
                watermark,
                self.count,
                order=order,
                role_ports=lambda t: mem.bank(t).ports,
            )
            ptr.prepare()
            self.pointers[key] = ptr
        ptr = self.pointers[key]
        state = self.parent_model.start(mem.rd.meta(r)).reshape(1, -1)
        _, state = ptr.logits(state, 0, torch.tensor([[pos]]))
        best, high = None, -float("inf")
        for off in range(0, len(eligible), 256):
            refs = eligible[off : off + 256]
            paths = torch.tensor([[pos, bank.positions[ref[:2]]] for ref in refs])
            logits, _ = ptr.logits(state.expand(len(refs), -1), 1, paths)
            index = int(logits.argmax())
            if float(logits[index]) > high:
                high, best = float(logits[index]), refs[index]
            self.count["open_partner_scores"] += len(refs)
            self.count["visits"] += len(refs)
        return best


@dataclass
class Instance:
    recipe: int
    mode: str
    depth: int
    boundary: dict
    tokens: list
    next_run: int


def live(store, ref, table):
    if ref is None:
        return False
    row = store.visible.get(ref[:2])
    return row is not None and row["table"] == table and row["version"] == ref[2]


class StructureEntries(PointerEntries):
    def __init__(self, program, store, *args):
        super().__init__(program, store, *args)
        self.menu = link(program, read(store / "structure-book.json"))
        self.programs = dict(item for options in self.menu.values() for item in options)
        self.codes = {}
        self.members = {}
        self.observed = {}
        self.pending = []
        self.instances = []
        self.needed = {
            op
            for plan in self.programs.values()
            for _, _, wires in plan
            for _, back, op in wires
            if back >= 0
        }

    def structure_options(self, r, j, base, depth, target, recent, option):
        if not target:
            return
        for pid, plan in self.menu.get(r, ()):
            key = j, pid
            if key not in self.codes:
                # Static downstream rule descriptors plus their source roles and
                # operator positions feed the SAME B scoring head as Primitive.
                code = base.copy()
                for rule, stage, wires in plan[1:]:
                    code += self.code(self.mem, rule, 0) / len(plan)
                    for role, (owner, back, op) in enumerate(wires):
                        code[(role + 2 * (owner + 2)) % len(code)] += (op + 2) / (16 * len(plan))
                    code[-1] += stage / (8 * len(plan))
                self.codes[key] = code
            for mode in ("Extend", "Compose") if depth and recent else ("Extend",):
                code = self.codes[key].copy()
                code[-3 if mode == "Extend" else -2] += 1
                option("Wired" + mode, code, pid)
                self.count["structure_scores"] += 1

    def start(self, rd, pub, txn, rules, stats):
        # Latch the first actual publication of program members. In particular,
        # later repair of the same token/op cannot retroactively supply a receipt.
        accepted = set(map(int, pub[3][:, 0]))
        for uid, _, tokens, _, step in self.waiting:
            for token in tokens:
                if token in accepted:
                    self.latch(rd, token)
            if step == len(self.cat.units[uid]):
                self.members[tokens[-1]] = tuple(tokens)
        for token, _, _, _ in self.publish_next:
            if token in accepted:
                self.latch(rd, token)
        for inst in self.pending:
            for token in inst.tokens:
                if token in accepted:
                    self.latch(rd, token)
        super().start(rd, pub, txn, rules, stats)
        self.struct_positions = defaultdict(dict)

    def latch(self, rd, token):
        for op in self.needed:
            row = rd.store.visible.get((token, op))
            if row is not None:
                self.observed[token, op] = token, op, int(row["version"])

    def issue_structure(self, r, refs, mode, mem, pid):
        plan = self.programs[pid]
        if any(rule not in self.rules for rule, stage, _ in plan if stage == 0):
            self.count["structure_entry_schedule_conflict"] += 1
            return
        boundary = {}
        for rule, stage, wires in plan:
            for table, wire in zip(mem.roles[rule], wires, strict=True):
                owner, back, op = wire
                if owner >= 0:
                    continue
                source = refs[-owner - 1]
                if back < 0:
                    ref = source
                else:
                    members = self.members.get(source[0], ())
                    ref = self.observed.get((members[-1 - back], op)) if back < len(members) else None
                if not live(mem.rd.store, ref, table):
                    self.count["structure_unavailable_entry"] += 1
                    return
                boundary[wire] = ref
        root = self.issue_suffix(r, refs, mode, mem)
        if root is None:
            return
        self.members[root] = (root,)
        self.count["structure_root_accepted"] += 1
        depth = self.suffix_tokens[root][1]
        self.suffix_tokens[root] = ("Wired" + mode, depth)
        inst = Instance(pid, mode, depth, boundary, [root], self.txn.run)
        self.instances.append(inst)
        if plan[1][1] == 0:
            self.advance(inst, mem)
        else:
            inst.next_run += 1
            self.pending.append(inst)

    def resume_programs(self, mem):
        waiting, self.pending = self.pending, []
        for inst in waiting:
            self.advance(inst, mem)

    def advance(self, inst, mem):
        plan = self.programs[inst.recipe]
        i = len(inst.tokens)
        group = plan[i][1]
        steps = [(r, wires) for r, stage, wires in plan[i:] if stage == group]
        if self.txn.run < inst.next_run or any(r not in self.rules for r, _ in steps):
            self.pending.append(inst)
            return
        for r, wires in steps:
            parents = tuple(
                inst.boundary[w] if w[0] < 0 else self.observed.get((inst.tokens[w[0]], w[2])) for w in wires
            )
            if not all(live(mem.rd.store, ref, t) for ref, t in zip(parents, mem.roles[r], strict=True)):
                self.count["structure_unavailable_return"] += 1
                return
            if mem.rd.iface.rules[r]["metadata"]["seminaive"] and all(p[2] < self.rules[r] for p in parents):
                self.count["structure_old"] += 1
                return
            if parents in self.done[r]:
                self.count["structure_already_done"] += 1
                return
            reply = send(self.txn, r, np.asarray([parents], np.int64))[0]
            self.count["structure_reply_" + STATUS[int(reply[1])]] += 1
            if reply[1] != 0:
                return
            tok = int(reply[0])
            branch = "fanout" if fanout(plan, len(inst.tokens)) else "continuation"
            self.suffix_tokens[tok] = (branch, inst.depth)
            self.publish_next.append((tok, r, inst.depth, tuple(p[0] for p in parents)))
            inst.tokens.append(tok)
            self.members[tok] = tuple(inst.tokens)
            self.done[r].add(parents)
            self.covered_rules[r] = self.done[r]
            self.covered_indices = {k: v for k, v in self.covered_indices.items() if k[0] != r}
            coords = tuple(mem.bank(t).positions[p[:2]] for t, p in zip(mem.roles[r], parents, strict=True))
            self.suffix_positions[r].add(coords)
            self.struct_positions[r][coords] = branch
            self.count["structure_wired_reads"] += len(parents)
        if len(inst.tokens) < len(plan):
            inst.next_run = self.txn.run + 1
            self.pending.append(inst)
        else:
            self.count["structure_completed"] += 1

    def structure_report(self, origins):
        credit = Counter()
        for tok, n in origins:
            credit[tok] += n
        return [
            {
                "pid": i.recipe,
                "mode": i.mode,
                "tokens": i.tokens,
                "root_ops": credit[i.tokens[0]],
                "extra_ops": sum(credit[t] for t in i.tokens[1:]),
                "boundary_refs": len(set(i.boundary.values())),
            }
            for i in self.instances
        ]
