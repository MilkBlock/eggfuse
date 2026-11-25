"""Instance-scoped, versioned CCP continuation. No query over unrelated evidence."""

from collections import defaultdict
from dataclasses import dataclass, field
from time import perf_counter

import numpy as np

from discrete_draft import Cell, Local
from higher_replacement import send
from scaling_native import Measured


@dataclass(eq=False)
class Instance:
    unit: list
    external: tuple
    owners: list = field(default_factory=list)
    versions: dict = field(default_factory=dict)
    awaiting: set = field(default_factory=set)


class Ownership(Measured):
    def __init__(self, *args):
        super().__init__(*args)
        self.watch = defaultdict(set)
        self.owned = {}
        self.outputs = {}
        self.m.forced_owned = self.forced_owned

    def forced_owned(self, rule, tab, hint, rng, stats):
        # The decoder has already selected the primitive; this fast path is valid
        # only for an empty draft prefix with one physical address in a unary role.
        if len(self.m.rows[tab]) != 1:
            return None
        addr = self.m.rows[tab][0]
        entry = self.confirmed.live.get(addr)
        if entry is None:
            return None
        refs = ((*addr, entry[0]["version"]),)
        if (rule, refs) not in self.owned:
            return None
        # Both outcomes of the copy coin resolve to the same physical address.
        # Preserve the original draw for subsequent edits in the stream.
        if (
            hint and hint.refs and not isinstance(hint.refs[0], Local) and hint.refs[0][:2] == addr
        ) or self.m.last == addr:
            rng.random()
        stats["avoided_singleton_reads"] += 1
        return Cell(rule, refs, False)

    def attach(self, inst, token, stats):
        rid = inst.unit[0][0]
        if rid not in self.outputs:
            ports = [set() for _ in inst.unit]
            for _, _, wires in inst.unit:
                for src, op in wires:
                    stats["compile_wire_reads"] += 1
                    if src >= 0:
                        ports[src].add(op)
            self.outputs[rid] = ports
        pos = len(inst.owners)
        inst.owners.append(token)
        for op in self.outputs[rid][pos]:
            addr = token, op
            stats["register_named_reads"] += 1
            if addr in inst.versions:
                continue
            if addr in self.confirmed.live:
                inst.versions.setdefault(addr, self.confirmed.live[addr][0]["version"])
            else:
                self.watch[addr].add(inst)
                inst.awaiting.add(addr)

    def close(self, inst):
        for addr in inst.awaiting:
            self.watch[addr].discard(inst)
            if not self.watch[addr]:
                del self.watch[addr]

    def send(self, items, txn, stats):
        if not items:
            return []
        # Only suffixes actually accepted in this snapshot own work. Retain
        # observation-bearing requests and all ordinary peer-to-peer duplicates.
        missing = []
        rows = [None] * len(items)
        for i, item in enumerate(items):
            c = item.cell
            row = self.owned.get((c.rule, c.refs)) if not c.higher and c.observe == 0 else None
            if row is None:
                missing.append(i)
            else:
                rows[i] = row
                stats["neural_primitive_receipt_reuses"] += 1
        for offset in range(0, len(missing), txn.capacity):
            indices = missing[offset : offset + txn.capacity]
            start = len(self.waiting)
            replies = super().send([items[i] for i in indices], txn, stats)
            for i, row in zip(indices, replies, strict=True):
                rows[i] = row
            for j in range(start, len(self.waiting)):
                unit, ext, owners, _ = self.waiting[j]
                inst = Instance(unit, ext)
                self.attach(inst, owners[0], stats)
                self.waiting[j] = inst
        stats["peak_open"] = max(stats["peak_open"], len(self.waiting))
        return rows

    def resume_programs(self, frame, pub, txn, stats):
        tick = perf_counter()
        self.owned.clear()
        if self.watch:
            for row in pub[0]:
                addr = int(row[0]), int(row[1])
                stats["publication_probes"] += 1
                if addr not in self.confirmed.live:
                    continue
                subs = self.watch.pop(addr, ())
                for inst in subs:
                    inst.awaiting.remove(addr)
                    inst.versions[addr] = self.confirmed.live[addr][0]["version"]
                    stats["publication_pins"] += 1
        scheduled = dict(frame["rules"])
        remaining = []
        for inst in self.waiting:
            rid, _, wires = inst.unit[len(inst.owners)]
            if rid not in scheduled:
                remaining.append(inst)
                continue
            refs = []
            stale = False
            for src, pc in wires:
                stats["named_receipt_reads"] += 1
                if src < 0:
                    token, op, ver = inst.external[pc]
                    addr = token, op
                else:
                    addr = inst.owners[src], pc
                    ver = inst.versions.get(addr)
                current = self.confirmed.live.get(addr)
                if ver is None or current is None or current[0]["version"] != ver:
                    # Once pinned, an exact version can never be reacquired after
                    # retirement/version advance. Unpublished conditionals may wake later.
                    stale = ver is not None and current is not None
                    break
                refs.append((*addr, ver))
            if stale:
                self.close(inst)
                stats["stale_released"] += 1
                continue
            if len(refs) != len(wires):
                stats["blocked_waits"] += 1
                remaining.append(inst)
                continue
            key = rid, tuple(refs)
            row = self.owned.get(key)
            if row is None:
                row = send(txn, rid, np.asarray(refs, np.int64).reshape(1, len(refs), 3))[0]
                stats["lowered_suffix"] += 1
                if row[1] != 0:
                    stats["suffix_rejected"] += 1
                    self.close(inst)
                    continue
                self.owned[key] = row.copy()
            else:
                stats["higher_overlap_reuses"] += 1
            self.attach(inst, int(row[0]), stats)
            if len(inst.owners) == len(inst.unit):
                stats["higher_completed"] += 1
                stats[f"completed/{len(inst.unit)}"] += 1
                self.close(inst)
            else:
                remaining.append(inst)
        self.waiting = remaining
        stats["open_instances"] = len(remaining)
        stats["continuation_seconds"] += perf_counter() - tick
