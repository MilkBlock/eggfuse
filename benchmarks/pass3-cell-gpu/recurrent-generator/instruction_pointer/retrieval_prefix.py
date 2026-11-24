"""Condition the frozen prefix scorer on the same complete tuple pool as Compose."""

import torch

from anchor_set import Domains
from history import History


class PrefixRead:
    def __init__(self, model, cat):
        self.model = model
        self.cat = cat
        self.nodes = model.template_graph(cat)
        self.history = History(cat, 3434, cache_ports=True)

    def advance(self, frame, active):
        snap = self.history.snapshot(frame, active)
        if snap is not None:
            self.mem = self.model.memory(self.cat, snap, self.nodes)
            self.index = {p.address: i for i, p in enumerate(self.mem.ports)}
            self.dom = Domains(self.mem)

    def scores(self, rid, pivot, keys):
        ids = torch.tensor(
            [[self.index[self.history.rename(key)] for key in ks] for ks in keys]
        )
        order = self.cat.read_order(rid, pivot, "source")
        logits = (
            self.model.root_scores(
                self.cat, self.mem, rid, pivot, ids[:, pivot], self.dom
            )
            - self.model.thresholds[1]
        )
        score = torch.nn.functional.logsigmoid(logits)
        for depth, role in enumerate(order[1:], 1):
            prior = order[:depth]
            for start in range(0, len(keys), 48):
                tmp = ids[start : start + 48]
                pre, pi = tmp[:, prior].unique(dim=0, return_inverse=True)
                choices, ci = tmp[:, role].unique(return_inverse=True)
                v = (
                    self.model.pair_scores(
                        self.cat, self.mem, rid, prior, pre, role, choices
                    )[pi, ci]
                    - self.model.thresholds[2]
                )
                score[start : start + len(tmp)] += torch.nn.functional.logsigmoid(v)
        return score.numpy()
