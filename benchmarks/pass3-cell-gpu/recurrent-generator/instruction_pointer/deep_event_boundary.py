"""Bind outer slots with B's frozen field postings and parent scorer; execute named Run groups."""

from collections import defaultdict

import numpy as np
import torch

from cell_stream import CellStream
from deep_event_rollout import DeepTemplates
from higher_replacement import send


class FullTemplates(DeepTemplates):
    def __init__(self, program, catalog_dir, size=None):
        super().__init__(program, catalog_dir, full=True, size=size)

    def start(self, rd, pub, txn, rules, stats):
        self.rules, self.count = rules, stats
        self.pointers = {}
        self.done = defaultdict(set)
        accepted = set(map(int, pub[3][:, 0]))
        assert self.expected <= accepted
        self.expected.clear()
        pending, self.waiting = self.waiting, []
        for uid, boundary, tokens, ports, next_step in pending:
            unit = self.cat.units[uid]
            # Latch actual named returns only on the publication after their producer.
            for _, _, wires in unit[next_step:]:
                for owner, pc in wires:
                    if owner >= 0 and owner < len(tokens) and (owner, pc) not in ports:
                        row = rd.store.visible.get((tokens[owner], pc))
                        ports[owner, pc] = (
                            None
                            if row is None
                            else (tokens[owner], pc, int(row["version"]))
                        )
            if next_step == len(unit):
                self.count["completed_deep"] += 1
                self.count[f"completed_size_{len(unit)}"] += 1
            else:
                self.group(uid, boundary, tokens, ports, next_step, txn)

    def group(self, uid, boundary, tokens, ports, start, txn):
        unit = self.cat.units[uid]
        epoch = unit[start][1]
        end = start + 1
        while end < len(unit) and unit[end][1] == epoch:
            end += 1
        if any(r not in self.rules for r, _, _ in unit[start:end]):
            if epoch == 0:
                self.count["root_schedule_conflict"] += 1
                return
            self.waiting.append((uid, boundary, tokens, ports, start))
            return
        for r, _, wires in unit[start:end]:
            parents = tuple(boundary[s] if i < 0 else ports[i, s] for i, s in wires)
            if any(ref is None for ref in parents):
                self.count["missing_return"] += 1
                return
            response = send(txn, r, np.asarray(parents, np.int64).reshape(1, -1, 3))[0]
            self.count["lowered_steps"] += 1
            if response[1] != 0:
                self.count["rejected_step"] += 1
                return
            tok = int(response[0])
            self.expected.add(tok)
            self.done[r].add(parents)
            tokens.append(tok)
        self.waiting.append((uid, boundary, tokens, ports, end))

    def bind(self, r, wires, target, boundary):
        mem = self.mem
        known = [j for j, (i, s) in enumerate(wires) if i < 0 and s in boundary]
        order = tuple(known + [target])
        key = r, order
        if key not in self.pointers:
            ptr = CellStream(
                mem.rd,
                self.parent_model,
                r,
                self.rules.get(r, 0),
                self.count,
                order=order,
                role_ports=lambda t: mem.bank(t).ports,
            )
            if not all(ptr.roles):
                return None
            ptr.prepare()
            self.pointers[key] = ptr
        ptr = self.pointers[key]
        prefix = np.array(
            [
                [
                    mem.bank(mem.roles[r][j]).positions[boundary[wires[j][1]][:2]]
                    for j in known
                ]
            ],
            dtype=np.int64,
        )
        h = self.parent_model.start(mem.rd.meta(r)).reshape(1, -1)
        for depth in range(len(known)):
            _, h = ptr.logits(h, depth, torch.from_numpy(prefix[:, : depth + 1]))
        post, start, count = mem.window(r, known, target, prefix)
        best = None
        high = 0.0
        for off in range(0, int(count[0]), 256):
            ix = np.arange(start[0] + off, start[0] + min(off + 256, count[0]))
            ix = ix if post is None else post[ix]
            paths = np.column_stack((np.repeat(prefix, len(ix), 0), ix))
            score, _ = ptr.logits(
                h.expand(len(ix), -1), len(known), torch.from_numpy(paths)
            )
            k = int(score.argmax())
            self.count["visits"] += len(ix)
            self.count["boundary_scores"] += len(ix)
            if score[k] >= 0 and (best is None or score[k] > high):
                best = int(ix[k])
                high = float(score[k])
        if best is None:
            return None
        return tuple(mem.bank(mem.roles[r][target]).rows[best])

    def begin(self, uid, row, tok, txn):
        self.count["higher_attempts"] += 1
        unit = self.cat.units[uid]
        boundary = {}
        for (_, slot), ref in zip(unit[0][2], map(tuple, row), strict=True):
            if slot in boundary and boundary[slot] != ref:
                self.count["root_wiring_conflict"] += 1
                return
            boundary[slot] = ref
        for r, _, wires in unit[1:]:
            for j, (owner, slot) in enumerate(wires):
                if owner < 0 and slot not in boundary:
                    ref = self.bind(r, wires, j, boundary)
                    if ref is None:
                        self.count["boundary_unbound"] += 1
                        return
                    boundary[slot] = ref
        self.count["higher_started"] += 1
        self.expected.add(tok)
        if unit[1][1] == 0:
            self.group(uid, boundary, [tok], {}, 1, txn)
        else:
            self.waiting.append((uid, boundary, [tok], {}, 1))
