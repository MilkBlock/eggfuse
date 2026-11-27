"""Shared nonlinear Cell readout using the existing decoder weights and native public fields."""

import math
import os

import torch

from binding_model import bit_lanes
from cell_kv_model import CellKV
from compatibility_study import baseline_path


def lane_products(words):
    # The only pairs constructed are inside one already-published port.
    width = max(map(len, words), default=0)
    bits = torch.from_numpy(
        bit_lanes([tuple(w) + (0,) * (width - len(w)) for w in words])
    )
    j, k = torch.triu_indices(width, width, offset=1)
    both = bits[:, j] * bits[:, k]
    lanes = (both[:, :, :32] + both[:, :, 32:]) * 0.5
    valid = k[None, :] < torch.tensor(list(map(len, words)))[:, None]
    # Fixed role code; no access to a Recipe guard, op, or target column.
    ordinal = k * (k - 1) // 2 + j + 1
    role = torch.cos(ordinal[:, None] * (torch.arange(32) + 0.5) * math.pi / 32)
    return lanes * valid[:, :, None], role


class ValueRead(CellKV):
    def __init__(self, a, variant):
        super().__init__(a, "C", False)
        self.variant = variant
        self.load_state_dict(
            torch.load(baseline_path(os.environ["ARTIFACT_ROOT"]), weights_only=True)
        )
        self.requires_grad_(False)
        for layer in (
            self.actor.query,
            self.actor.input_role,
            self.actor.lanes,
            self.actor.next_read,
        ):
            layer.requires_grad_(True)

    def read_interface(self, query, ports):
        if self.variant != "C":
            return None
        lanes, role = lane_products([p[4] for p in ports])
        return torch.einsum("td,pfd,fh->tph", query.softmax(-1), lanes, role)

    def template_readout(self, ctx, read, codes):
        if self.variant != "A":
            recipe = self.actor.input_role(codes)
            recipe = recipe.expand_as(read)
            joint = self.actor.next_read(
                read.reshape(-1, 32), recipe.tanh().reshape(-1, 32)
            ).reshape_as(read)
            read = read + joint
        return super().template_readout(ctx, read, codes)

    def singleton(self, codes, val, ext, lanes, role):
        """Batch-equivalent entry read for exactly one public owner with one port."""
        lane = self.actor.lanes.weight[0].expand_as(val)
        # Softmax over one item has weight one at both address reductions.
        ctx = self.actor.next_read(val, lane)
        read = (val + ext)[:, None, :].expand(-1, len(codes), -1)
        if self.variant == "C":
            q = self.actor.query(ctx[:, None] + codes)
            read = read + torch.einsum("btd,bfd,fh->bth", q.softmax(-1), lanes, role)
        return self.template_readout(ctx[:, None], read, codes).log_softmax(-1)
