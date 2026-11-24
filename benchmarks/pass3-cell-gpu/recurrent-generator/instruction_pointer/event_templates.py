"""Emit a variable-size set of Bake template/role addresses from a published port."""

from collections import defaultdict
import math
import numpy as np
import torch
from torch import nn
from event_addresses import PAGE

SHAPE = 14


def shape(rd, r, j):
    rule = rd.iface.rules[r]
    roles = rd.iface.roles[r]
    effects = rule["effects"]
    columns = roles[j][1] if j >= 0 else ()
    slots = set(v for v in columns if v is not None)
    return [
        len(roles) / 8,
        len(rule["query"]) / 12,
        len(effects) / 12,
        len(columns) / 8,
        j / 8,
        float(rule["metadata"]["seminaive"]),
        len(slots) / 8,
        sum(len(slots.intersection(v for v in vs if v is not None)) for _, vs in roles)
        / 12,
        sum("primitive" in a["call"] for a in rule["query"]) / 8,
        *[
            sum(e["op"] == op for e in effects) / 8
            for op in ("let", "set", "union", "copy", "hide")
        ],
    ]


class BranchNet(nn.Sequential):
    def __init__(self):
        super().__init__(
            nn.Linear(16 + SHAPE * 2 + 2, 64),
            nn.Tanh(),
            nn.Linear(64, 32),
            nn.Tanh(),
            nn.Linear(32, 1),
        )


class Node:
    def __init__(self, labels, values, depth=0):
        self.labels = frozenset(labels)
        self.code = np.r_[
            values.mean(0),
            np.ptp(values, axis=0),
            math.log1p(len(labels)) / 8,
            depth / 12,
        ].astype(np.float32)
        self.children = []
        self.label = labels[0] if len(labels) == 1 else None
        if len(labels) > 1:
            perm = values[:, values.var(0).argmax()].argsort(kind="stable")
            for part in np.array_split(perm, 2):
                self.children.append(
                    Node([labels[i] for i in part], values[part], depth + 1)
                )


class TemplateTree:
    def __init__(self, rd):
        groups = defaultdict(list)
        for r, roles in enumerate(rd.iface.roles):
            for j, (tab, _) in enumerate(roles):
                groups[rd.tabs[tab]].append((r, j))
            if not roles:
                groups[-1].append((r, -1))
        self.groups = groups
        self.roots = {
            t: Node(ls, np.array([shape(rd, *q) for q in ls], np.float32))
            for t, ls in groups.items()
        }
        self.minimum = {}
        self.schedule = None

    def prepare(self, rules):
        # Only static subscriptions and per-rule watermarks enter this index.
        def visit(node):
            if node.label is not None:
                w = rules.get(node.label[0], float("inf"))
            else:
                w = min(visit(c) for c in node.children)
            self.minimum[node] = w
            return w

        for root in self.roots.values():
            visit(root)

    def blocks(self, mem, rules):
        self.prepare(rules)
        mem.stats["schedule_metadata_nodes"] += len(self.minimum)
        for t, root in self.roots.items():
            wm = self.minimum[root]
            if wm == float("inf"):
                continue
            if t < 0:
                yield (
                    t,
                    root,
                    np.array([0]),
                    np.zeros((1, 16), np.float32),
                    np.array([2**62]),
                )
            else:
                bank = mem.bank(t)
                ix = bank.version_order[np.searchsorted(bank.versions, wm) :]
                for start in range(0, len(ix), PAGE):
                    a = ix[start : start + PAGE]
                    yield t, root, a, bank.vec[a], bank.rows[a, 2]

    @staticmethod
    def features(vec, node):
        return np.column_stack(
            (vec, np.broadcast_to(node.code, (len(vec), len(node.code))))
        )

    def emit(self, mem, rules, model, cuts, stats):
        for t, root, ix, vec, ver in self.blocks(mem, rules):
            stats["source_port_reads"] += len(ix) if t >= 0 else 0
            pending = [(root, np.arange(len(ix)))]
            while pending:
                node, ids = pending.pop()
                ids = ids[ver[ids] >= self.minimum[node]]
                if not len(ids):
                    continue
                x = self.features(vec[ids], node)
                prob = model(torch.from_numpy(x)).flatten().numpy()
                stats["template_branch_scores"] += len(ids)
                threshold = cuts["boot" if t < 0 else "cell"]
                ids = ids[prob >= threshold] if threshold is not None else ids
                if not len(ids):
                    continue
                if node.label is not None:
                    yield *node.label, ix[ids]
                else:
                    pending.extend((c, ids) for c in reversed(node.children))
