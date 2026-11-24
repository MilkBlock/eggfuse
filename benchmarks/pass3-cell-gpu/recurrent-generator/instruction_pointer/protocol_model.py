"""Neural readout of CCP value bytes and a decoder over individual Bake instructions."""

from collections import defaultdict

import numpy as np
import torch
from torch import nn

from txn_policy import ReadPlan

RAW = 39
WIDTH = 16


def value_inputs(response):
    """Read every byte of every returned value, including nested set/key payloads.

    Keep type, eight positional bytes and positional pooled payload features.
    Losslessness belongs to the wire, not to this finite embedding.
    """
    ends = response.value_ends.astype(np.int64)
    n = len(response.rows)
    out = np.zeros((n, RAW), np.float32)
    if not len(ends) or not ends[-1]:
        return torch.from_numpy(out)
    starts = np.r_[0, ends[:-1]]
    sizes = ends - starts
    active = sizes > 0
    owners = np.repeat(np.arange(n), sizes)
    positions = np.arange(len(owners)) - starts[owners]
    data = response.values
    out[np.nonzero(active)[0], data[starts[active]]] = 1
    out[:, 6] = np.log1p(sizes)
    short = (positions > 0) & (positions <= 8)
    out[owners[short], 6 + positions[short]] = data[short] / 255.0
    buckets = (positions * 13 + data.astype(np.int64) * 7) % 24
    np.add.at(out, (owners, 15 + buckets), 1.0)
    out[:, 15:] /= np.maximum(1, sizes[:, None])
    return torch.from_numpy(out)


class ProtocolNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.value = nn.Sequential(
            nn.Linear(RAW, WIDTH), nn.Tanh(), nn.Linear(WIDTH, WIDTH)
        )
        self.structure = nn.Linear(4, 8)
        self.status = nn.Linear(4, 8)
        self.proof = nn.Sequential(
            nn.Linear(WIDTH + 16, 32), nn.Tanh(), nn.Linear(32, 1)
        )
        self.instruction = nn.Sequential(nn.Linear(10, 24), nn.Tanh(), nn.Linear(24, 1))
        self.operand = nn.Sequential(nn.Linear(5, 12), nn.Tanh(), nn.Linear(12, 1))
        self.scope = nn.Linear(10 + WIDTH, 1)
        self.boundary = nn.Sequential(
            nn.Linear(10 + WIDTH, 24), nn.Tanh(), nn.Linear(24, 3)
        )
        self.query = nn.Sequential(
            nn.Linear(WIDTH + 3, 16), nn.Tanh(), nn.Linear(16, 1)
        )

    def score(self, static, value, state):
        return self.proof(
            torch.cat((self.structure(static), value, self.status(state)), 1)
        ).flatten()


def decode(model, rd, rule, depth, capacity, stats, example=None):
    """A single-step action vocabulary plus STOP. No host enumeration of programs."""
    roles = rd.iface.roles[rule]
    order = rd.order(rule)
    target = roles[order[depth]][1]
    available = defaultdict(list)
    for j, role in enumerate(order[:depth]):
        for c, slot in enumerate(roles[role][1]):
            if slot is not None:
                available[slot].append((j, c))
    rule_ir = rd.iface.rules[rule]
    atoms = rule_ir["query"]
    sorts = [s["sort"]["name"] for s in rule_ir["slots"]]
    instructions = [(pc, a) for pc, a in enumerate(atoms) if "primitive" in a["call"]]
    history = []
    outputs = []
    used = set()
    for step in range(min(len(instructions), capacity) + 1):
        terminal = bool(outputs and outputs[-1] in target)
        feats = [[1, terminal, 0, 0, 0, 0, 0, step / 8, depth / 8, 0]]
        actions = [None]
        for pc, a in instructions:
            args = a["args"][:-1]
            out = a["args"][-1].get("slot")
            if pc in used or out is None or not args or step >= capacity:
                continue
            choices = []
            for arg in args:
                if "literal" in arg:
                    choices.append([None])
                    continue
                slot = arg["slot"]
                options = list(available.get(slot, []))
                # CCP accepts earlier scalar results of the expected sort. Their
                # instruction provenance still matters to the chosen program.
                options.extend(
                    ("local", j)
                    for j, v in enumerate(outputs)
                    if v != slot and sorts[v] == sorts[slot]
                )
                choices.append(options)
            if not all(choices):
                continue
            consumers = sum(
                any(x.get("slot") == out for x in b["args"][:-1])
                for other, b in instructions
                if other != pc
            )
            feats.append(
                [
                    0,
                    terminal,
                    out in target,
                    consumers / 4,
                    len(args) / 4,
                    pc / max(1, len(atoms)),
                    sum(any(t and t[0] == "local" for t in opts) for opts in choices)
                    / 4,
                    step / 8,
                    depth / 8,
                    sum(len(opts) for opts in choices) / 8,
                ]
            )
            actions.append((pc, out, choices))
        x = torch.tensor(feats, dtype=torch.float)
        if example is not None:
            teacher, records, operands = example
            wanted = teacher[step][0] if step < len(teacher) else None
            ix = next(
                i for i, v in enumerate(actions) if (v[0] if v else None) == wanted
            )
            records.append((x, ix))
        else:
            ix = int(model.instruction(x).argmax())
            stats["instruction_decisions"] += 1
        if actions[ix] is None:
            if example is None:
                stats["program_stops"] += 1
                stats["neural_controls"] += 1
            break
        pc, out, choices = actions[ix]
        selected = []
        for i, opts in enumerate(choices):

            def features(opt, position):
                if opt is None:
                    return [1, 0, 0, 0, 0]
                local = opt[0] == "local"
                return [
                    0,
                    local,
                    (opt[1] if local else opt[0]) / 8,
                    opt[1] / 8,
                    position / 8,
                ]

            ox = torch.tensor([features(opt, i) for opt in opts], dtype=torch.float)
            if example is not None:
                which = opts.index(teacher[step][1][i])
                if len(opts) > 1:
                    operands.append((ox, which))
            else:
                which = int(model.operand(ox).argmax()) if len(opts) > 1 else 0
                stats["operand_choices" if len(opts) > 1 else "singleton_operands"] += 1
            selected.append(opts[which])
        history.append((pc, tuple(selected)))
        outputs.append(out)
        available[out].append(("local", step))
        used.add(pc)
    if history and outputs[-1] in target:
        pc, args = history[-1]
        return [ReadPlan(pc, args, target.index(outputs[-1]), tuple(history[:-1]))]
    return []
