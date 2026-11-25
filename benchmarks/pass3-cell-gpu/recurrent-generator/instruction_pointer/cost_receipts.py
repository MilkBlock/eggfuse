"""Offline oracle for the already frozen positive, executable evidence region catalog."""

from collections import defaultdict

import numpy as np

from cost_bake import CostBake
from evidence_execution import EvidenceEntries
from evidence_regions import PARTNER
from recursive_train import read
from ripsat_layout import signatures


class ReceiptOracle(EvidenceEntries):
    combined = False
    single = False
    learned_cost = False

    def __init__(self, program, store, *args):
        super().__init__(program, store, *args)
        sha = program["recipe"]["sha256"]
        choices = read(store / (sha + "-receipts.json"))
        self.choices = defaultdict(list)
        for q in choices[:1] if self.single else choices:
            table, fields = q["stamp"]
            self.choices[q["run"], q["op"], q["version"], table, tuple(fields)].append(q)
        self.chosen = {}
        if self.combined:
            sig = signatures(program)
            menu = set(map(tuple, read(store / "cost-book.json")["entries"]))
            events = None
            if not self.learned_cost:
                choices = np.load(store / (sha + "-oracle.npz"))["events"]
                events = defaultdict(set)
                for run, r, j, t, pc, v in choices:
                    events[run, r, j].add((t, pc, v))
            entries = {
                (r, j)
                for r, s in enumerate(sig)
                for j in range(len(program["recipe"]["rules"][r]["interface"]["rows"]))
                if (s, j) in menu
            }
            self.cost_bake = CostBake(self, entries, events)

    def select_region(self, mem, token, outputs, pids):
        pc = min(outputs)
        t, _, v = outputs[pc]
        row = mem.rd.store.visible[t, pc]
        key = (self.txn.run, pc, v, row["table"], tuple(map(int, row["hashes"])))
        self.count["oracle_receipt_source_reads"] += 1
        queue = self.choices.get(key, [])
        for i, q in enumerate(queue):
            if q["recipe"] in pids:
                self.chosen[token] = q
                queue.pop(i)
                return q["recipe"]
        return None

    def bind_partner(self, region, mem):
        q = self.chosen[region.source]
        ref = tuple(q["other"])
        row = mem.rd.store.visible.get(ref[:2])
        self.action_counts["EvidenceBind"] += 1
        region.partner_reads += 1
        if (
            row is not None
            and row["version"] == ref[2]
            and [row["table"], list(map(int, row["hashes"]))] == q["other_stamp"]
        ):
            region.boundary[PARTNER, 0] = ref
            region.independent += 1


class SingleReceiptOracle(ReceiptOracle):
    single = True


class CombinedOracle(ReceiptOracle):
    combined = True


class ReceiptWithFrozenB(CombinedOracle):
    """Re-evaluate the eight-entry choice on live IDs after early receipt publication."""

    learned_cost = True
