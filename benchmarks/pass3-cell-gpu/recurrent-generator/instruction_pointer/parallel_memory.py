"""Static scalar templates share the proof template tree and GNN operand nodes."""

from collections import defaultdict
from dataclasses import dataclass

import torch

from response_plan import ResponseMemory
from response_study import memory


@dataclass(frozen=True)
class Scalar:
    rule: int
    atom: int
    roles: tuple
    operands: tuple

    def wire(self, refs):
        return [
            (0, -1, 0, 0) if item is None else (*refs[item[0]], item[1])
            for item in self.operands
        ]


def scalars(r, contract):
    roles = {slot["atom"]: i for i, slot in enumerate(contract["inputs"])}
    for comp in contract["computations"]:
        inputs = []
        operands = []
        for operand in comp["operands"]:
            if "literal_operand" in operand:
                operands.append(None)
            else:
                fields = [(roles[a], c) for a, c in operand["fields"] if a in roles]
                if not fields:
                    break
                role, col = fields[0]
                if role not in inputs:
                    inputs.append(role)
                operands.append((inputs.index(role), col))
        else:
            yield Scalar(r, comp["atom"], tuple(inputs), tuple(operands))


class SetMemory(ResponseMemory):
    def __init__(self, enc, contract, menu, scorer):
        super().__init__(enc, contract, menu, scorer)
        self.scalars = {}
        self.by_rule = defaultdict(list)
        graph = []
        for r, rc in enumerate(contract["rules"]):
            for desc in scalars(r, rc):
                idx = len(self.roles)
                self.scalars[idx] = desc
                self.by_rule[r].append(idx)
                self.roles.append(tuple(self.roles[r][i] for i in desc.roles))
                enc.cat.inputs["generated", idx] = [
                    enc.cat.inputs["generated", r][i] for i in desc.roles
                ]
                self.output_tables.append({})
                self.projections.append({})
                graph.append(
                    (
                        enc.graphs[r] + enc.nodes[enc.cat.query_nodes[r, desc.atom]]
                    ).tanh()
                )
        if graph:
            enc.graphs = torch.cat((enc.graphs, torch.stack(graph)))
        self.draft_pool = None

    def template_options(self, rules):
        return [
            key
            for r in rules
            for key in (
                *super(SetMemory, self).template_options((r,)),
                *((v, False) for v in self.by_rule[r]),
            )
        ]

    def context(self):
        base = super().context()
        return base if self.draft_pool is None else (base + self.draft_pool).tanh()

    def observe_reply(self, items, replies):
        self.reply(
            [
                (i.cell, int(replies[i.uid][1]) in (0, 14))
                for i in items
                if i.uid in replies
            ]
        )


def make_memory(a, d):
    return memory(a, d, memory_type=SetMemory)
