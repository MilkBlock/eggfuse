"""Dense reads inside one published port. No interaction between different owners."""

import math

import torch

from binding_model import bit_lanes
from value_read_model import ValueRead


def position(ids):
    return torch.cos((ids[..., None] + 1) * (torch.arange(32) + 0.5) * math.pi / 32)


def words(rows):
    width = max(map(len, rows))
    padded = [tuple(row) + (0,) * (width - len(row)) for row in rows]
    return torch.from_numpy(bit_lanes(padded)), position(torch.arange(width))


def repeated_argument(args):
    seen = set()
    for i, arg in enumerate(args):
        slot = arg.get("slot")
        if slot is not None:
            if slot in seen:
                return i
            seen.add(slot)
    return None


def operand_nodes(w):
    """Select static query operand nodes only. No physical field offsets are returned."""
    edges = {
        (dst, role // 2 - 2): src
        for src, dst, role in w.cat.edges
        if role >= 4 and role % 2 == 0
    }
    ids = []
    for layout in w.layouts:
        # Use the earliest constrained input. Unconstrained templates use their entry atom.
        rid = layout[0][0]
        inputs = w.cat.inputs["generated", rid]
        fallback = inputs[0] if inputs else w.cat.roots["generated", rid]
        operands = [fallback, fallback]
        for rid, _, _ in layout:
            queries = w.prog["recipe"]["rules"][rid]["query"]
            prim = next(
                (
                    i
                    for i, q in enumerate(queries)
                    if q["call"].get("primitive") == "!="
                ),
                None,
            )
            if prim is not None:
                n = w.cat.query_nodes[rid, prim]
                operands = [edges[n, 0], edges[n, 1]]
                break
            for i, q in enumerate(queries):
                if "table" not in q["call"]:
                    continue
                n = w.cat.query_nodes[rid, i]
                duplicate = repeated_argument(q["args"])
                if duplicate is not None:
                    operands = [edges[n, duplicate]] * 2
                    break
            else:
                continue
            break
        ids.append(operands)
    return torch.tensor(ids)


class OperandRead(ValueRead):
    def __init__(self, a, arm):
        super().__init__(a, "C")
        self.reader = arm
        self.audit = False

    def prepare(self, w):
        super().prepare(w)
        self.entry_menu = w.menu([w.root])
        if self.reader == "D":
            if not hasattr(w, "reader_operand_nodes"):
                w.reader_operand_nodes = operand_nodes(w)
            self.descriptors = self.cache[0][w.reader_operand_nodes]

    def state(self, w, s):
        self.menu = s["menu"]
        return super().state(w, s)

    def payload(self, q, fields, roles, valid, menu):
        # q [batch, templates, 32], fields [batch, fields, 64].
        arm = self.reader
        if arm == "B":
            j, k = torch.triu_indices(len(roles), len(roles), offset=1)
            pair_keys = position(k * (k - 1) // 2 + j)
            logits = q @ pair_keys.T / math.sqrt(32)
            mask = valid[:, None, j] & valid[:, None, k]
            values = fields[:, j] * fields[:, k]
            weights = logits.masked_fill(~mask, -1e9).softmax(-1) * mask
            out = weights @ values
            probe = q
        else:
            signals = self.actor.lanes.weight[1:3]
            if arm == "D":
                signals = signals + self.descriptors[menu]
            probe = self.actor.query(q.unsqueeze(-2) + signals)
            logits = probe @ roles.T / math.sqrt(32)
            mask = valid[:, None, None, :]
            weights = logits.masked_fill(~mask, -1e9).softmax(-1) * mask
            operands = torch.einsum("btmf,bfd->btmd", weights, fields)
            out = operands[:, :, 0] * operands[:, :, 1]
        if self.audit:
            self.trace = (weights, probe)
        return (out[..., :32] + out[..., 32:]) * 0.5

    def read_interface(self, query, ports):
        fields, roles = words([p[4] for p in ports])
        valid = (
            torch.arange(len(roles))[None, :]
            < torch.tensor([len(p[4]) for p in ports])[:, None]
        )
        return self.payload(
            query.expand(len(ports), -1, -1), fields, roles, valid, self.menu
        ).transpose(0, 1)

    def singleton(self, codes, val, ext, fields, roles):
        ctx = self.actor.next_read(val, self.actor.lanes.weight[0].expand_as(val))
        q = self.actor.query(ctx[:, None] + codes)
        valid = torch.ones(fields.shape[:2], dtype=torch.bool)
        read = (val + ext)[:, None] + self.payload(
            q, fields, roles, valid, self.entry_menu
        )
        return self.template_readout(ctx[:, None], read, codes).log_softmax(-1)
