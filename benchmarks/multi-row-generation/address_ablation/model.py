"""Learned source and generated-token pointer retrieval with four rotary layouts.

A demand is a semantic origin address. The physical candidate index is predicted
by attention. Only that predicted index is used to gather an origin or payload.
"""
import math

import torch
from torch import nn


ARMS = ('flat', 'two', 'three', 'packed')


class RotaryAddress(nn.Module):
    """Rotate all width coordinates, split evenly among the active address axes."""

    def __init__(self, arm, width):
        super().__init__()
        if arm not in ARMS or width <= 0 or width % 12:
            raise ValueError('known address arm and a positive width divisible by 12 required')
        self.arm = arm
        self.axes = {'flat': 1, 'two': 2, 'three': 3, 'packed': 1}[arm]
        self.pairs = width // (2 * self.axes)
        exponent = torch.arange(self.pairs, dtype=torch.float32) / self.pairs
        self.register_buffer('frequencies', torch.exp(-math.log(10000) * exponent), persistent=False)

    def coordinates(self, coords, length, ports):
        row, position, port = coords.unbind(dim=-1)
        if self.arm == 'three':
            return coords
        if self.arm == 'two':
            return coords[..., :2]
        address = row * length + position
        if self.arm == 'packed':
            address = address * ports + port
        return address.unsqueeze(-1)

    def angles(self, coords, length, ports):
        positions = self.coordinates(coords, length, ports).to(self.frequencies.dtype)
        angles = positions.unsqueeze(-1) * self.frequencies
        return angles.cos(), angles.sin()

    def rotate(self, vectors, angles):
        even, odd = vectors.reshape(*vectors.shape[:-1], self.axes, self.pairs, 2).unbind(-1)
        cos, sin = angles
        return torch.stack((even * cos - odd * sin, even * sin + odd * cos), dim=-1).flatten(-3)


class Pointer(nn.Module):
    """Independent learned queries and keys with common content and rotary score widths."""

    def __init__(self, width):
        super().__init__()
        self.query = nn.Linear(width, 2 * width)
        self.key = nn.Linear(width, 2 * width)
        self.scale = 1 / math.sqrt(2 * width)

    def forward(self, queries, candidates, rotary, query_angles, candidate_angles):
        q_content, q_rotary = self.query(queries).chunk(2, dim=-1)
        k_content, k_rotary = self.key(candidates).chunk(2, dim=-1)
        q = torch.cat((q_content, rotary.rotate(q_rotary, query_angles)), dim=-1)
        k = torch.cat((k_content, rotary.rotate(k_rotary, candidate_angles)), dim=-1)
        return (q @ k.transpose(-1, -2)) * self.scale


def gather_rows(rows, pointer):
    if rows.ndim == 2:
        return rows.gather(1, pointer)
    return rows.gather(1, pointer.unsqueeze(-1).expand(-1, -1, rows.shape[-1]))


class AddressModel(nn.Module):
    """One graph per batch item, with multiple rows and ports in its candidate bank.

    Input coordinate triples are (row, token position, ordinal port), with
    0 <= position < length and 0 <= port < ports. These strides describe the
    address space, including unused positions and ports. Both demands refer to
    original source coordinates. Run 2 sees only its demand and emitted tokens.
    """

    def __init__(self, arm, width=48):
        super().__init__()
        self.arm = arm
        self.rotary = RotaryAddress(arm, width)
        # All arms see these same real-valued port features, including flat and
        # packed. They accept new ordinals without an embedding-table lookup.
        self.port = nn.Sequential(nn.Linear(5, width), nn.Tanh(), nn.Linear(width, width))
        self.first = Pointer(width)
        self.second = Pointer(width)
        self.emit = nn.Sequential(nn.Linear(width + 1, width), nn.Tanh(), nn.Linear(width, width))
        self.read = nn.Linear(width, width)

    def port_content(self, coords, ports):
        p = coords[..., 2].to(self.rotary.frequencies.dtype)
        relative = p / max(ports - 1, 1)
        features = torch.stack((p, relative, relative.square(),
                                torch.cos(math.pi * relative), torch.sin(math.pi * relative)), dim=-1)
        return self.port(features)

    def _score(self, scorer, query_coords, candidate_coords, keys, length, ports):
        queries = self.port_content(query_coords, ports)
        return scorer(queries, keys, self.rotary,
                      self.rotary.angles(query_coords, length, ports),
                      self.rotary.angles(candidate_coords, length, ports))

    def address_scores(self, stage, query_coords, candidate_coords, length, ports, *, candidate_latent=None):
        """Score all supplied slots. A 'make' scorer needs addresses only.

        'finish' is the generated-frontier scorer and also requires that
        frontier's actual AddressModel latent; no synthetic default is supplied.
        Candidate coordinates may be [N,3] (common layout) or [B,N,3].
        """
        keys = self.port_content(candidate_coords, ports)
        if stage == 'make':
            if candidate_latent is not None:
                raise ValueError('the source pointer only accepts addresses')
            scorer = self.first
        elif stage == 'finish':
            if candidate_latent is None:
                raise ValueError('finish scoring requires the generated candidate latent')
            keys = keys + self.read(candidate_latent)
            scorer = self.second
        else:
            raise ValueError('stage must be make or finish')
        return self._score(scorer, query_coords, candidate_coords, keys, length, ports)

    def finish_from(self, pair_origin, pair_value, pair_latent, finish_ref, length, ports):
        """Query a generated Pair bank, using the physical slot index only after argmax."""
        scores = self.address_scores('finish', finish_ref, pair_origin, length, ports,
                                     candidate_latent=pair_latent)
        pointer = scores.argmax(-1)
        return dict(scores2=scores, ptr2=pointer, result_value=gather_rows(pair_value, pointer))

    def forward(self, coords, make_ref, finish_ref, value, length, ports):
        if length < 1 or ports < 1 or coords.ndim != 2 or coords.shape[-1] != 3:
            raise ValueError('expected source coordinates [N,3] with positive address strides')
        if value.ndim != 2 or value.shape[1] != coords.shape[0]:
            raise ValueError('expected source value [B,N]')
        if any(r.ndim != 3 or r.shape[0] != value.shape[0] or r.shape[-1] != 3
               for r in (make_ref, finish_ref)):
            raise ValueError('expected batched [B,demands,3] origin address demands')
        batch = value.shape[0]
        source = self.port_content(coords, ports).unsqueeze(0).expand(batch, -1, -1)
        scores = self._score(self.first, make_ref, coords, source, length, ports)
        pointer = scores.argmax(-1)
        origin = gather_rows(coords.unsqueeze(0).expand(batch, -1, -1), pointer)
        payload = gather_rows(value, pointer)
        selected = gather_rows(source, pointer)
        if self.training:
            # Forward carries the actual selected row. The soft read contributes
            # a surrogate gradient to Run 1 logits for the downstream pointer loss.
            soft = scores.softmax(-1) @ source.detach()
            selected = selected + (soft - soft.detach())
        latent = self.emit(torch.cat((selected, payload.to(selected.dtype).unsqueeze(-1)), dim=-1))
        finish = self.finish_from(origin, payload, latent, finish_ref, length, ports)
        return dict(scores1=scores, ptr1=pointer, pair_origin=origin, pair_value=payload,
                    pair_latent=latent, **finish)
