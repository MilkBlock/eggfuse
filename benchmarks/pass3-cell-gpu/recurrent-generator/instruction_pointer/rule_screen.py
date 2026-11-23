"""Shared learned rule selection from static Cell structure and sealed Run receipts."""
from bisect import bisect_left
from collections import defaultdict
from math import log1p

import torch
from torch import nn


class RuleScreen(nn.Module):
    def __init__(self, width=32):
        super().__init__()
        self.head = nn.Sequential(nn.Linear(width+8, width), nn.Tanh(), nn.Linear(width, 1))
        self.register_buffer('threshold', torch.tensor(0.0))

    def forward(self, features):
        return self.head(features).flatten()


class RuleContext:
    def __init__(self):
        self.last = {}
        self.run = 0

    def observe(self, frame):
        run = frame['run']
        if run != self.run + 1:
            raise ValueError('rule history missed a source Run')
        self.run = run
        for receipt in frame['accepted']:
            if receipt['run'] != run-1:
                raise ValueError('rule receipt is from outside the previous Run')
            self.last[receipt['rule']] = run-1

    def features(self, catalog, snapshot, nodes):
        if snapshot.run != self.run:
            raise ValueError('unsealed rule input')
        versions = defaultdict(list)
        for port in snapshot.ports:
            versions[port.table].append(port.version)
        for rows in versions.values():
            rows.sort()
        counts = {}
        rows, roots = [], []
        for rule, watermark in snapshot.rules.items():
            visible, fresh = [], []
            for table, _ in catalog.atoms[rule]:
                if (table,watermark) not in counts:
                    timestamps = versions[table]
                    counts[table,watermark] = (len(timestamps),len(timestamps)-bisect_left(timestamps,watermark))
                size, delta = counts[table,watermark]
                visible.append(size)
                fresh.append(delta)
            age = snapshot.run - self.last[rule] if rule in self.last else 0
            rows.append([log1p(len(fresh)), log1p(min(visible,default=0)),log1p(sum(visible)),
                         log1p(max(fresh,default=0)),log1p(sum(fresh)),float(rule in self.last),
                         log1p(age),float(catalog.seminaive[rule])])
            roots.append(catalog.roots['generated',rule])
        return torch.cat((nodes[roots],nodes.new_tensor(rows).reshape(-1,8)),dim=1)


class LiveRuleScreen:
    def __init__(self, model):
        self.model = model
        self.history = RuleContext()

    def select(self, catalog, snapshot, nodes):
        scores = self.model(self.history.features(catalog,snapshot,nodes))
        return {r for r,keep in zip(snapshot.rules,(scores>=self.model.threshold).tolist(),strict=True) if keep}
