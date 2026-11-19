"""Encode a static Bake port graph. Only frozen deployment caches its embeddings."""

from dataclasses import dataclass

import torch
from torch import nn
import torch.nn.functional as F


def vocab(values):
    return {v: i + 1 for i, v in enumerate(sorted(set(values)))}


@dataclass
class PortGraph:
    local: torch.Tensor  # node sort, kind, ordered operand position
    incident: torch.Tensor  # raw per-node counts for each directed relation
    adjacency: torch.Tensor  # [relation, receiver, sender], normalized
    readouts: torch.Tensor  # [stage, pointer operand]
    identity: torch.Tensor  # learned only for training templates


class GraphSchema:
    """Fit all categorical vocabularies on the training partition only."""

    def __init__(self, training):
        self.kinds = vocab(n["kind"] for t in training for n in t["graph"]["nodes"])
        self.sorts = vocab(str(n["sort"]) for t in training for n in t["graph"]["nodes"])
        self.ordinals = vocab(int(n["ordinal"]) for t in training for n in t["graph"]["nodes"])
        self.rels = vocab(
            (way, str(r))
            for t in training
            for _, r, _ in t["graph"]["edges"]
            for way in ("in", "out")
        )
        self.ids = vocab(t["id"] for t in training)
        # An operand readout represents a whole source row. Preserve the
        # compiler role of EACH ordered column even in the message-free baseline.
        self.column_capacity = 8
        self.column_role_width = 6 + len(self.sorts) + 1
        self.base_width = (
            sum(len(v) + 1 for v in (self.kinds, self.sorts, self.ordinals))
            + self.column_capacity * self.column_role_width
        )
        self.rel_width = len(self.rels) + 1

    def pack(self, t, device):
        graph = t["graph"]
        nodes = graph["nodes"]
        columns = []
        for field, mapping in [
            ("kind", self.kinds),
            ("sort", self.sorts),
            ("ordinal", self.ordinals),
        ]:
            ids = [
                mapping.get(int(n[field]) if field == "ordinal" else str(n[field]), 0)
                for n in nodes
            ]
            columns.append(F.one_hot(torch.tensor(ids), num_classes=len(mapping) + 1).float())
        role = torch.zeros(len(nodes), self.column_capacity, self.column_role_width)
        for stage, (spec, readers) in enumerate(zip(t["stages"], graph["readouts"])):
            for side, reader in enumerate(readers):
                fields = spec["left_sorts" if side == 0 else "right_sorts"]
                if len(fields) > self.column_capacity:
                    raise ValueError("operand exceeds declared column capacity")
                for col in range(len(fields)):
                    point = [side, col]
                    flags = role[reader, col]
                    flags[0] = 1  # present
                    flags[1] = float(stage == 1 and side == 0)  # published by preceding Run
                    for x, y in spec["checks"]:
                        for arg, other in ((x, y), (y, x)):
                            if arg == point:
                                flags[2 if other[0] == 2 else 3 if other[0] == side else 4] += 1
                    flags[5] = spec["outputs"].count(point)
                    # Coarse typed recipe kind of this actual source column.
                    nc = [
                        v
                        for u, r, v in graph["edges"]
                        if u == reader and r == "reads" and nodes[v]["ordinal"] == col
                    ]
                    if len(nc) != 1:
                        raise ValueError("missing or repeated compiler source column")
                    flags[6 + self.sorts.get(str(nodes[nc[0]]["sort"]), 0)] = 1
        columns.append(role.flatten(1))
        adjacency = torch.zeros(self.rel_width, len(nodes), len(nodes))
        for i, r, j in graph["edges"]:
            adjacency[self.rels.get(("in", str(r)), 0), j, i] += 1
            adjacency[self.rels.get(("out", str(r)), 0), i, j] += 1
        degrees = adjacency.sum(-1)
        normalized = adjacency / degrees.clamp_min(1)[..., None]
        return PortGraph(
            torch.cat(columns, -1).to(device),
            degrees.T.contiguous().to(device),
            normalized.to(device),
            torch.tensor(graph["readouts"], dtype=torch.long, device=device),
            torch.tensor(self.ids.get(t["id"], 0), dtype=torch.long, device=device),
        )


class GraphLayer(nn.Module):
    def __init__(self, width, relations):
        super().__init__()
        self.relation = nn.Parameter(torch.randn(relations, width) * 0.05)
        self.update = nn.Sequential(nn.Linear(2 * width, width), nn.GELU(), nn.Linear(width, width))
        self.norm = nn.LayerNorm(width)

    def forward(self, h, g, neighbors):
        if neighbors:
            # One incoming mean per typed directed relation, then a learned feature-wise gate.
            messages = g.adjacency @ h
        else:
            # Same parameters. Role-only MLP sees adjacency counts but no adjacent node identity.
            messages = h.unsqueeze(0).expand(g.adjacency.shape[0], -1, -1)
        weights = g.incident.T.clamp(max=1)[..., None] * self.relation[:, None, :]
        summary = (messages * weights).sum(0)
        return self.norm(h + self.update(torch.cat((h, summary), -1)))


class TemplateEncoder(nn.Module):
    def __init__(self, schema, width, variant):
        super().__init__()
        self.variant = variant
        self.local = nn.Linear(schema.base_width, width)
        self.out = nn.Sequential(nn.Linear(2 * width, width), nn.LayerNorm(width))
        if variant == "id":
            # Index zero always has a fixed zero embedding for an unseen template.
            self.identity = nn.Embedding(len(schema.ids) + 1, width, padding_idx=0)
        elif variant in ("roles", "pooled", "ports"):
            self.role = nn.Linear(schema.base_width + schema.rel_width, width)
            self.layers = nn.ModuleList([GraphLayer(width, schema.rel_width) for _ in range(2)])
        else:
            raise ValueError(variant)

    def forward(self, g):
        direct = self.local(g.local[g.readouts])
        if self.variant == "id":
            structural = self.identity(g.identity).expand_as(direct)
        else:
            h = self.role(torch.cat((g.local, g.incident.log1p()), -1))
            for layer in self.layers:
                h = layer(h, g, self.variant != "roles")
            structural = h.mean(0).expand_as(direct) if self.variant == "pooled" else h[g.readouts]
        return self.out(torch.cat((direct, structural), -1))
