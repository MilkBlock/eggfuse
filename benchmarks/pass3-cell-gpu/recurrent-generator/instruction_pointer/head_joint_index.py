"""A publication-local joint neural index. No raw field values enter this module."""

from dataclasses import dataclass

import torch

from partner_index import EXPLORE, categorical

RADIX = 1 << 19
SCALE = 1 << 32


def halves(features):
    ids, values = features
    if ids.size(1) != 4 or ids.size(-1) != 2:
        raise ValueError("requires four heads with two interpolation terms each")
    for head in (0, 2):
        hi, lo = ids[:, head].long(), ids[:, head + 1].long()
        key = hi.unsqueeze(-1) * RADIX + lo.unsqueeze(-2)
        weight = values[:, head].unsqueeze(-1) * values[:, head + 1].unsqueeze(-2)
        yield key.flatten(-2), weight.flatten(-2)


def ranks(dictionary, keys):
    # An absent half must never alias the next greater half at its insertion point.
    flat = keys.flatten(1).contiguous()
    offset = torch.searchsorted(dictionary, flat)
    size = dictionary.size(1)
    found = (offset < size) & (dictionary.gather(1, offset.clamp_max(size - 1)) == flat)
    return torch.where(found, offset, size).view_as(keys)


def entries(parts, dictionaries):
    (a, p), (b, q) = parts
    hi, lo = (ranks(d, k) for d, k in zip(dictionaries, (a, b), strict=True))
    code = hi.unsqueeze(-1) * (dictionaries[1].size(1) + 1) + lo.unsqueeze(-2)
    return code.flatten(-2), (p.unsqueeze(-1) * q.unsqueeze(-2)).flatten(-2)


@dataclass
class PostingIndex:
    dictionaries: tuple
    keys: torch.Tensor
    ends: torch.Tensor
    owners: torch.Tensor

    @classmethod
    def build(cls, features, row_weight):
        n = row_weight.size(1)
        # Future weights sum to N, including on edges of deeper trees.
        if not n or (4 * n + 1) ** 2 >= 2**63 or n * SCALE >= 2**62:
            raise ValueError("publication size outside signed int64 range")
        parts = tuple(halves(features))
        dictionaries = tuple(k.flatten(1).sort().values.contiguous() for k, _ in parts)
        code, mass = entries(parts, dictionaries)
        keys, order = code.flatten(1).sort()
        units = ((mass * row_weight.unsqueeze(-1)) * SCALE).round().long()
        ends = torch.nn.functional.pad(
            units.flatten(1).gather(1, order).cumsum(1), (1, 0)
        )
        return cls(dictionaries, keys, ends, (order // 16).int())

    def lookup(self, features):
        keys, q = entries(tuple(halves(features)), self.dictionaries)
        flat = keys.flatten(1).contiguous()
        lo = torch.searchsorted(self.keys, flat)
        hi = torch.searchsorted(self.keys, flat, right=True)
        start = self.ends.gather(1, lo).view_as(keys)
        count = self.ends.gather(1, hi).view_as(keys) - start
        return start, count, q * (count.float() / SCALE)


@dataclass
class Edge:
    index: PostingIndex
    start: torch.Tensor
    count: torch.Tensor
    mass: torch.Tensor

    def draw(self, roots, u):
        gather = roots.unsqueeze(-1).expand(-1, -1, 16)
        mass = self.mass.gather(1, gather)
        ch = categorical(mass, u[..., :1])
        start = self.start.gather(1, gather).gather(2, ch).squeeze(-1)
        count = self.count.gather(1, gather).gather(2, ch).squeeze(-1)
        offset = torch.minimum(
            (u[..., 1] * count.float()).long(), (count - 1).clamp_min(0)
        )
        pos = (
            torch.searchsorted(
                self.index.ends, (start + offset).contiguous(), right=True
            )
            - 1
        )
        owners = self.index.owners
        hit = owners.gather(1, pos.clamp(0, owners.size(1) - 1)).long()
        n = owners.size(1) // 16
        fallback = (u[..., 2] * n).long().clamp_max(n - 1)
        return torch.where((mass.sum(-1) <= 0) | (u[..., 3] < EXPLORE), fallback, hit)


def prepare(model, data):
    # The frozen map emits floor(t) and floor(t)+1 for 0 <= t <= resolution.
    # Check the static layout before constructing fixed-width half keys.
    if model.mapping.resolution + 1 >= RADIX:
        raise ValueError("projection resolution exceeds the joint coordinate width")
    inp, layout = data
    future = [b[0].new_zeros(b[0].shape[:2]) for b in inp[3]]
    edges = [None] * len(layout)
    for j in reversed(range(1, len(future))):
        parent, cols = layout[j - 1]
        v = model.encode(inp[3][j][1], cols[:, :, 1])
        q = model.encode(inp[3][parent][1], cols[:, :, 0])
        index = PostingIndex.build(v, future[j].softmax(1) * future[j].size(1))
        edge = Edge(index, *index.lookup(q))
        # Strictly positive exploration for unrepresented branches at intermediate stages.
        future[parent] += (edge.mass.sum(-1) + 1e-12).log()
        edges[j - 1] = edge
    p = (model.local.root_prior(inp) + future[0]).softmax(-1)
    return p * (1 - EXPLORE) + EXPLORE / p.size(1), edges


def draw(data, state, u):
    p, edges = state
    refs = [categorical(p, u[:, :, 0, 0, 0])]
    for j, (parent, _) in enumerate(data[1], 1):
        refs.append(edges[j - 1].draw(refs[parent], u[:, :, j, 0]))
    return torch.stack(refs, -1)
