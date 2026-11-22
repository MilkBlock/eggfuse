"""Content attention over exports visible at a Run boundary, for the existing two-row actor."""
from math import sqrt

import torch
from torch import nn

from model import Actor, HIDDEN


class PortContextActor(Actor):
    def __init__(self, features):
        super().__init__()
        self.key = nn.Linear(features, HIDDEN)
        self.value = nn.Linear(features, HIDDEN)
        self.query = nn.Linear(HIDDEN, HIDDEN)
        self.mix = nn.Linear(HIDDEN, HIDDEN, bias=False)

    def encode_ports(self, features):
        return self.key(features), self.value(features)

    def metal_weights(self):
        raise NotImplementedError("port context requires the PyTorch checkpoint format")

    def step(self, observations, previous, intervention='intact', context_adjust=None,
             score_adjust=None, forbidden=None, *, ports=None):
        state = self.proposal_queries(observations, previous, intervention)
        if ports is None or ports[0].shape[1] == 0:
            return self._emit(observations, state, context_adjust, score_adjust, forbidden)
        keys, values, live = ports
        query = self.query(state.tanh())
        scores = query @ keys.transpose(1, 2) / sqrt(HIDDEN)
        scores = scores.masked_fill(~live[:, None], torch.finfo(scores.dtype).min)
        weights = scores.softmax(-1) * live[:, None]
        adjustment = self.mix(weights @ values)
        if context_adjust is not None:
            adjustment = adjustment + context_adjust
        return self._emit(observations, state, adjustment, score_adjust, forbidden)


class ExportMemory:
    """One policy with frozen weights. Accepted exports enter at a snapshot boundary."""
    def __init__(self, actor):
        if actor.training:
            raise ValueError("cached projections require a frozen evaluation checkpoint")
        self.actor = actor
        self.rows = {}
        self.encoded = 0

    @torch.no_grad()
    def publish(self, replacements, retired=()):
        # Caller supplies actual export identities and current content, including
        # any changed equivalence/scalar features. Never infer identity from a vector.
        retired = set(retired)
        if retired.intersection(replacements):
            raise ValueError("ambiguous retirement and replacement")
        if any(k in self.rows and version < self.rows[k][0]
               for k,(version,_) in replacements.items()):
            raise ValueError("port version moved backwards")
        changed = sorted(k for k, item in replacements.items()
                         if k not in self.rows or self.rows[k][:2] != item)
        if changed:
            features = self.actor.key.weight.new_tensor([replacements[k][1] for k in changed])
            keys, values = self.actor.encode_ports(features)
            for i, k in enumerate(changed):
                version, fields = replacements[k]
                self.rows[k] = (version, fields, keys[i], values[i])
        for k in retired:
            self.rows.pop(k, None)
        self.encoded += len(changed)

    def snapshot(self):
        # Canonical order makes reductions independent of arrival/storage order.
        ordered = [self.rows[k] for k in sorted(self.rows)]
        if ordered:
            keys, values = [torch.stack([row[column] for row in ordered]) for column in (2, 3)]
        else:
            keys = values = self.actor.key.weight.new_empty((0,HIDDEN))
        live = torch.ones((1,len(ordered)),dtype=torch.bool,device=keys.device)
        return keys[None], values[None], live
