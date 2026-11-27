"""Dense attention over named ports conditioned on the fields of a concrete prefix."""

import math
from types import MethodType

from operand_read_model import words


def static_wires(w, rid, j):
    rows = w.prog["recipe"]["rules"][rid]["interface"]["rows"]
    # The graph edge number encodes the static argument position (Catalog.edge).
    if not hasattr(w, "prefix_operands"):
        w.prefix_operands = {
            (dest, edge // 2 - 2): source
            for source, dest, edge in w.cat.edges
            if edge >= 4 and edge % 2 == 0
        }
    inputs = []
    for prev in range(j):
        for src, col in w.cat.field_links[rid, prev, j]:
            node = w.prefix_operands[w.cat.query_nodes[rid, rows[j]["atom"]], col]
            inputs.append((prev, src, col, node))
    inputs.sort(key=lambda link: (link[2], link[0], link[1]))
    return tuple(inputs)


def attach(n):
    # Keep static metadata in the World, never learned tensors across updates.
    original = n.address

    def address(self, w, m, tid, prefix):
        base = original(w, m, tid, prefix)
        if base is None or not prefix:
            return base
        rid = w.layouts[tid][0][0]
        j = len(prefix)
        if not hasattr(w, "prefix_wires"):
            w.prefix_wires = {}
        key = rid, j
        if key not in w.prefix_wires:
            w.prefix_wires[key] = static_wires(w, rid, j)
        wires = w.prefix_wires[key]
        if not wires:
            return base
        if "prefix_bits" not in m:
            m["prefix_bits"] = words([p[4] for p in m["ports"]])[0].reshape(
                len(m["ports"]), -1, 2, 32
            )
        # Incidental padding on other port types is excluded by the existing decoder.
        fields = m["prefix_bits"]
        pri, src, col, operand = zip(*wires, strict=True)
        selected = [prefix[i] for i in pri]
        role = self.cache[0][list(operand)][:, None, :]
        values = self.actor.latent(fields[:, list(col)]).tanh()
        filled = self.actor.latent(fields[selected, list(src)]).tanh()
        q = filled + 0.25 * self.actor.query(filled + role).tanh()
        k = values + 0.25 * self.actor.input_content(values + role).tanh()
        if getattr(self, "probe_relation", False):
            m.setdefault("probe_tensors", []).append((q, k, filled, values))
        relation = (q * k).sum(dim=(-1, -2)).sum(-1) / math.sqrt(64 * len(wires))
        return (base + relation).log_softmax(0)

    n.address = MethodType(address, n)
    return n
