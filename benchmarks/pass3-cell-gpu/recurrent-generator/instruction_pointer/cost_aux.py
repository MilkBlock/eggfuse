"""Per-call ledger for the two residual search paths outside the ordinary Cell Stream."""

from collections import Counter
from time import perf_counter

from protocol_experiment import dump
from structure_runtime import StructureEntries


class AuxiliaryProfile(StructureEntries):
    def __init__(self, program, store, *args):
        super().__init__(program, store, *args)
        self.log = []
        self.store = store
        self.nested = 0

    def measure(self, kind, r, role, sources, operation, *args):
        before = self.count["visits"]
        child_before = self.nested
        start = perf_counter()
        result = operation(*args)
        duration = perf_counter() - start
        visits = self.count["visits"] - before - (self.nested - child_before)
        self.nested += visits
        self.log.append(
            {
                "run": self.txn.run,
                "kind": kind,
                "rule": r,
                "role": role,
                "sources": sources,
                "result": [int(x) for x in result] if result is not None else None,
                "visits": visits,
                "inclusive_seconds": duration,
            }
        )
        return result

    def open_partner(self, r, j, pos, src, target, recent, mem, mode):
        return self.measure(
            "partner",
            r,
            j,
            [list(map(int, src))],
            super().open_partner,
            r,
            j,
            pos,
            src,
            target,
            recent,
            mem,
            mode,
        )

    def bind(self, r, wires, target, boundary):
        sources = [(int(i), *map(int, boundary[i])) for owner, i in wires if owner < 0 and i in boundary]
        return self.measure("boundary", r, target, sources, super().bind, r, wires, target, boundary)

    def audit_partners(self, data, case, work, result):
        output = self.store / f"{case}-auxiliary.json"
        dump(output, self.log)
        costs = Counter()
        for row in self.log:
            costs[row["kind"]] += row["visits"]
        expected = result["work"]["visits"] - result["work"]["parent_candidate_scores"]
        if sum(costs.values()) != expected:
            raise AssertionError(f"Unattributed auxiliary candidates: {expected - sum(costs.values())}")
        return {"auxiliary_visits": costs, "calls": len(self.log)}
