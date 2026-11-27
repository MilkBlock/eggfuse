"""Read schema-qualified public columns from a permuted per-port neural field store."""

import math
import random
from functools import lru_cache

import torch

from operand_read_model import OperandRead, position


@lru_cache(maxsize=128)
def layouts(width):
    identity = tuple(range(width))
    if width < 3:
        return (identity,), (tuple(reversed(identity)),)
    held = [tuple(reversed(identity)), identity[2:] + identity[:2]]
    rng = random.Random(915 + width)
    train = [identity]
    while len(train) < min(4, math.factorial(width) - len(held)):
        perm = tuple(rng.sample(identity, width))
        if perm not in train and perm not in held:
            train.append(perm)
    return tuple(train), tuple(held)


def operand_contract(w, layout):
    """Trace two guard arguments to a single entry row through explicit copies only."""
    unknown = (-1, -1)
    published = {}
    for step, (rid, _, wires) in enumerate(layout):
        rule = w.prog["recipe"]["rules"][rid]
        tables = [q for q in rule["query"] if "table" in q["call"]]
        if len(tables) != 1 or len(wires) != 1:
            return unknown
        args = tables[0]["args"]
        source = wires[0]
        if step == 0 and source == (-1, 0):
            cols = list(range(len(args)))
        else:
            row = published.get(source)
            if row is None or row[0] != tables[0]["call"]["table"]:
                return unknown
            cols = row[1]
        if cols is None or len(cols) != len(args):
            return unknown
        bound = {}
        for arg, col in zip(args, cols, strict=True):
            slot = arg.get("slot")
            if slot is None:
                continue
            if slot in bound:
                return (bound[slot], col) if min(bound[slot], col) >= 0 else unknown
            bound[slot] = col
        for q in rule["query"]:
            if q["call"].get("primitive") == "!=":
                origins = tuple(bound.get(arg.get("slot"), -1) for arg in q["args"][:2])
                return origins if min(origins) >= 0 else unknown
        for pc, e in enumerate(rule["effects"]):
            if e["op"] == "copy":
                bound[e["dst"]] = bound.get(e["arg"].get("slot"), -1)
            elif e.get("kind") == "construct":
                # A fresh result witness has no entry column.
                table = e["call"]["table"]
                refs = [bound.get(arg.get("slot"), -1) for arg in e["args"]] + [-1]
                for op, contract in w.contract["rules"][rid]["outputs"].items():
                    if (
                        contract["producer"] == "effect"
                        and contract["effect"] == pc
                        and w.tabs[contract["table"]] == table
                    ):
                        published[step, int(op)] = table, refs
    return unknown


class RoleRead(OperandRead):
    def __init__(self, a, arm):
        super().__init__(a, "D")
        self.arm_name = arm
        self.physical = ("train", 0)
        self.layout_rng = random.Random(6601)
        self.hard = False

    def prepare(self, w):
        super().prepare(w)
        if self.training:
            self.physical = ("train", self.layout_rng.randrange(4))
        if self.arm_name == "C":
            if not hasattr(w, "entry_operand_columns"):
                w.entry_operand_columns = torch.tensor(
                    [operand_contract(w, body) for body in w.layouts]
                )
            self.columns = w.entry_operand_columns
            self.type_codes = self.cache[2]
            self.entry_tables = [
                w.roles[body[0][0]][0] if w.roles[body[0][0]] else -1
                for body in w.layouts
            ]
            self.root_table = w.roles[w.root][0]

    def read_interface(self, query, ports):
        if self.arm_name == "C":
            self.port_types = self.type_codes[[p[3] for p in ports]]
        return super().read_interface(query, ports)

    def singleton(self, codes, val, ext, fields, roles):
        if self.arm_name == "C":
            self.port_types = self.type_codes[self.root_table].expand(len(val), -1)
        return super().singleton(codes, val, ext, fields, roles)

    def payload(self, q, fields, roles, valid, menu):
        b, f, _ = fields.shape
        split, idx = self.physical
        cols = torch.arange(f).repeat(b, 1)
        for n in set(valid.sum(-1).tolist()):
            orders = layouts(n)[split == "held"]
            cols[valid.sum(-1) == n, :n] = torch.tensor(
                orders[idx % len(orders)], dtype=torch.long
            )
        physical = fields.gather(1, cols[:, :, None].expand_as(fields))
        if self.arm_name != "C":
            return super().payload(q, physical, roles, valid, menu)
        # The native table qualifies the column namespace. The same public-role encoder
        # is shared across tables. No row, parent or template is filtered by the contract.
        column = self.columns[menu]
        tables = torch.tensor([self.entry_tables[t] for t in menu])
        declared = self.type_codes[tables.clamp_min(0)] * (tables >= 0)[:, None]
        static = (
            position(column.clamp_min(0)) * (column >= 0)[:, :, None]
            + 0.25 * declared[:, None]
        )
        query = (
            self.actor.query(
                q[:, :, None] + self.actor.lanes.weight[1:3] + self.descriptors[menu]
            )
            + static * 2
        )
        encoded = roles[cols] + 0.25 * self.port_types[:, None]
        keys = encoded + self.actor.input_role(encoded).tanh()
        halves = physical.reshape(b, f, 2, 32)
        values = (
            halves
            + 0.25
            * self.actor.input_role(
                halves + 0.25 * self.port_types[:, None, None]
            ).tanh()
        ).reshape_as(physical)
        logits = torch.einsum("btmd,bfd->btmf", query, keys) / math.sqrt(32)
        weights = (
            logits.masked_fill(~valid[:, None, None, :], -1e9).softmax(-1)
            * valid[:, None, None, :]
        )
        if self.hard:
            # Offline intervention on supported singleton entries. Other templates keep
            # their learned read. Inputs are static IR column IDs; no value is compared.
            matches = (cols[:, None, None, :] == column[None, :, :, None]) & valid[
                :, None, None, :
            ]
            weights = torch.where(
                matches.any(-1, keepdim=True), matches.to(q.dtype), weights
            )
        operands = torch.einsum("btmf,bfd->btmd", weights, values)
        relation = (
            (operands[:, :, 0] * operands[:, :, 1]).reshape(b, -1, 2, 32).mean(-2)
        )
        read = relation + self.actor.input_role(relation).tanh()
        if self.audit:
            self.role_trace = (query, keys, values, relation, weights, cols)
        return read
