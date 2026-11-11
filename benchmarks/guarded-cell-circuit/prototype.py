#!/usr/bin/env python3
"""Bounded semantic experiment, NOT an EggFuse/GPU runtime or benchmark.

Symbolically saturate a finite positive Horn fragment without enumerating
boundary assignments. Lower its shared guards to exact threshold gates, then
exhaustively check against an independently implemented union-find oracle.
Only the verification step enumerates input assignments.
"""
import itertools
import json
import struct
from functools import cache


def require(condition, message):
    if not condition:
        raise AssertionError(message)


PAIRS = list(itertools.combinations(range(4), 2))
INPUTS = [f"union:{i}:{j}" for i, j in PAIRS] + ["rule:pair", "rule:union"]


class BDD:
    """Small reduced ordered BDD used OFFLINE for semantic sharing."""

    def __init__(self):
        self.nodes = [(len(INPUTS), 0, 0), (len(INPUTS), 1, 1)]
        self.unique = {}

    def node(self, variable, low, high):
        if low == high:
            return low
        key = (variable, low, high)
        if key not in self.unique:
            self.unique[key] = len(self.nodes)
            self.nodes.append(key)
        return self.unique[key]

    @cache
    def op(self, kind, a, b):
        if a > b:
            return self.op(kind, b, a)
        if a == b:
            return a
        if kind == "and":
            if a == 0 or b == 0:
                return 0
            if a == 1:
                return b
        else:
            if a == 1 or b == 1:
                return 1
            if a == 0:
                return b
        variable = min(self.nodes[a][0], self.nodes[b][0])
        al, ah = self.nodes[a][1:] if self.nodes[a][0] == variable else (a, a)
        bl, bh = self.nodes[b][1:] if self.nodes[b][0] == variable else (b, b)
        return self.node(variable, self.op(kind, al, bl), self.op(kind, ah, bh))

    def evaluate(self, root, bits):
        while root > 1:
            variable, low, high = self.nodes[root]
            root = high if bits[variable] else low
        return root


def eq(level, i, j):
    return f"E:{level}:{min(i, j)}:{max(i, j)}"


def fragment(depth):
    """Four boundary ports; F chains; Pair(a,c), Pair(b,d); possible Hs.

    Pair(x,x) -> H(x); H(x) -> union(x,b). Separate readiness inputs
    gate these two rules. They do not represent source Run semantics.
    H-presence is membership modulo equality, not constructor allocation.
    """
    seeds = {eq(0, i, j): k for k, (i, j) in enumerate(PAIRS)}
    seeds.update({"ready:pair": 6, "ready:union": 7})
    clauses = []
    for level in range(depth + 1):
        for i, j, k in itertools.combinations(range(4), 3):
            edges = [eq(level, i, j), eq(level, i, k), eq(level, j, k)]
            for head in edges:
                clauses.append((head, tuple(x for x in edges if x != head)))
        if level:
            clauses.extend((eq(level, i, j), (eq(level - 1, i, j),)) for i, j in PAIRS)
    clauses.append(("pair-equal", (eq(0, 0, 1), eq(0, 2, 3))))
    for i, j in [(0, 2), (1, 3)]:
        clauses.append((f"H:{i}", ("ready:pair", eq(0, i, j))))
    for i in range(4):
        if i != 1:
            clauses.append((eq(0, i, 1), ("ready:union", f"H:{i}")))
        for j in range(4):
            if i != j:
                clauses.append((f"H:{j}", (f"H:{i}", eq(0, i, j))))
    for i, j in PAIRS:
        clauses.append((f"H-equal:{i}:{j}", (f"H:{i}", f"H:{j}", eq(0, i, j))))
    outputs = sorted(set(seeds) | {head for head, _ in clauses})
    outputs = [name for name in outputs if not name.startswith("ready:")]
    return seeds, clauses, outputs


def compile_fragment(depth):
    bdd = BDD()
    seeds, clauses, outputs = fragment(depth)
    guards = {name: bdd.node(index, 0, 1) for name, index in seeds.items()}
    rounds = 0
    while True:
        rounds += 1
        changed = False
        for head, body in clauses:
            proof = 1
            for atom in body:
                proof = bdd.op("and", proof, guards.get(atom, 0))
            old = guards.get(head, 0)
            new = bdd.op("or", old, proof)
            changed |= new != old
            guards[head] = new
        if not changed:
            return bdd, {name: guards[name] for name in outputs}, len(clauses), rounds


def reference(depth, bits):
    """Independent closure: unions and actual enabled pairs, no Horn/BDD calls."""
    parent = list(range(4))

    def find(x):
        while x != parent[x]:
            x = parent[x]
        return x

    def union(a, b):
        a, b = find(a), find(b)
        if a == b:
            return False
        parent[a] = b
        return True

    for enabled, (i, j) in zip(bits, PAIRS):
        if enabled:
            union(i, j)
    produced = set()
    while True:
        previous = set(produced)
        if bits[6]:
            for i, j in [(0, 2), (1, 3)]:
                if find(i) == find(j):
                    produced.add(i)
        changed = produced != previous
        if bits[7]:
            for i in sorted(produced):
                changed = union(i, 1) or changed
        if not changed:
            break
    present = [any(find(i) == find(j) for j in produced) for i in range(4)]
    result = {eq(level, i, j): int(find(i) == find(j))
              for level in range(depth + 1) for i, j in PAIRS}
    result["pair-equal"] = int(find(0) == find(1) and find(2) == find(3))
    result.update({f"H:{i}": int(present[i]) for i in range(4)})
    result.update({f"H-equal:{i}:{j}": int(present[i] and present[j] and find(i) == find(j))
                   for i, j in PAIRS})
    return result


class Network:
    """Static sparse threshold rows; IDs are wires, never runtime e-class IDs.

    AND(x,y) = H(x+y-1.5); OR(x,y) = H(x+y-0.5).
    All nonconstant gates have fan-in two. Exact binary16 sums are <= 2.
    No GPU kernel or dense matrix allocation is implemented here.
    """

    def __init__(self, bdd):
        self.bdd = bdd
        self.gates = []
        self.unique = {}
        self.levels = [0] * (2 + len(INPUTS))

    def gate(self, kind, a, b):
        a, b = sorted((a, b))
        if a == b:
            return a
        if kind == "and":
            if a == 0:
                return 0
            if a == 1:
                return b
        else:
            if a == 0:
                return b
            if a == 1:
                return 1
        key = (kind, a, b)
        if key not in self.unique:
            self.unique[key] = 2 + len(INPUTS) + len(self.gates)
            self.gates.append(key)
            self.levels.append(1 + max(self.levels[a], self.levels[b]))
        return self.unique[key]

    @cache
    def lower(self, root):
        if root < 2:
            return root
        variable, low, high = self.bdd.nodes[root]
        # All guards are monotone. Thus Shannon's mux simplifies to
        # low OR (variable AND high), with no learned or approximate weights.
        require(self.bdd.op("and", low, high) == low, "nonmonotone guard")
        return self.gate("or", self.lower(low),
                         self.gate("and", variable + 2, self.lower(high)))

    def evaluate(self, bits):
        values = [0, 1] + list(bits)
        for kind, a, b in self.gates:
            total = float(values[a] + values[b])
            bias = -1.5 if kind == "and" else -0.5
            # Exercise binary16 rounding explicitly, not a GPU timing claim.
            rounded = struct.unpack("e", struct.pack("e", total + bias))[0]
            values.append(int(rounded > 0))
        return values

    def evaluate_packed(self, cases):
        # One bit per independent instance; Python integers only validate
        # bit-sliced semantics. They are not GPU words or a hardware benchmark.
        columns = [sum(bits[i] << row for row, bits in enumerate(cases))
                   for i in range(len(INPUTS))]
        values = [0, (1 << len(cases)) - 1] + columns
        for kind, a, b in self.gates:
            values.append(values[a] & values[b] if kind == "and" else values[a] | values[b])
        return values


def verify(depth):
    bdd, roots, clauses, rounds = compile_fragment(depth)
    net = Network(bdd)
    outputs = {name: net.lower(root) for name, root in roots.items()}
    cases = list(itertools.product((0, 1), repeat=len(INPUTS)))
    packed = net.evaluate_packed(cases)
    for row, bits in enumerate(cases):
        expected = reference(depth, bits)
        symbolic = {name: bdd.evaluate(root, bits) for name, root in roots.items()}
        values = net.evaluate(bits)
        threshold = {name: values[wire] for name, wire in outputs.items()}
        require(symbolic == expected, f"symbolic mismatch: {depth}, {bits}")
        require(threshold == expected, f"threshold mismatch: {depth}, {bits}")
        require({name: (packed[wire] >> row) & 1 for name, wire in outputs.items()} == expected,
                f"packed mismatch: {depth}, {bits}")
    # Pair(a,c) is not diagonal initially; union(a,c) must enable H(a)
    # and the second rule must feed back into boundary equality a=b.
    bits = [0] * len(INPUTS)
    bits[PAIRS.index((0, 2))] = bits[6] = bits[7] = 1
    observed = reference(depth, bits)
    require(observed["H:0"] == observed[eq(depth, 0, 1)] == 1,
            "union-enabled rule / feedback was lost")
    bits[6] = 0
    require(reference(depth, bits)["H:0"] == 0, "inactive rule executed")
    # Every F level shares the guard; no repeated runtime propagation chain.
    require(all(roots[eq(0, i, j)] == roots[eq(level, i, j)]
                for level in range(1, depth + 1) for i, j in PAIRS),
            "congruence chain was not shared")
    reachable = set()

    def visit(root):
        if root > 1 and root not in reachable:
            reachable.add(root)
            _, low, high = bdd.nodes[root]
            visit(low)
            visit(high)

    for root in roots.values():
        visit(root)
    return {"chain_depth": depth, "checked_assignments": len(cases),
            "packed_batch_checked": True,
            "logical_output_projections": len(outputs),
            "ground_horn_clauses": clauses, "offline_fixpoint_sweeps": rounds,
            "offline_bdd_nodes_allocated": len(bdd.nodes) - 2,
            "reachable_bdd_nodes": len(reachable),
            "distinct_output_guards": len(set(roots.values())),
            "threshold_gates": len(net.gates), "threshold_depth": max(net.levels),
            "output_map_entries_if_exporting_all": len(outputs)}


if __name__ == "__main__":
    results = [verify(depth) for depth in (1, 8, 64)]
    require(len({r["threshold_gates"] for r in results}) == 1,
            "longer congruence chain increased the runtime network")
    print(json.dumps({"status": "pass", "scope": "standalone-bounded-semantic-prototype",
                      "gpu_execution": False, "runtime_takeover": False,
                      "timing_claim": False, "results": results}, indent=2))
