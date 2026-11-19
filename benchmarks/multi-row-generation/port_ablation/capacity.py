"""Widen the shared pointer scorer for the parameter-count sensitivity control.

With input width D and R rules, both factors have shape [R*D,D], giving 2*R*D²
parameters. The effective score matrix Wq.T @ Wk still has rank at most D.
The extra factors can change optimization, but still realize one bilinear map
shared across rules. Independent rule heads can realize R different maps.
"""
import torch
from torch import nn


class WideSharedPointerHead(nn.Module):
    """Single rule-independent scorer initialized from a fitted-or-unfitted square head."""

    def __init__(self, base_head, num_rules, *, seed=0):
        super().__init__()
        if num_rules < 1:
            raise ValueError('num_rules must be positive')
        key_weight = base_head.key.weight
        query_weight = base_head.query.weight
        dim = key_weight.shape[1]
        if (key_weight.shape != (dim, dim) or query_weight.shape != key_weight.shape
                or base_head.query.bias is not None or base_head.key.bias is not None):
            raise ValueError('expected square, bias-free source query/key projections')
        width = num_rules * dim
        # nn.Linear initializes its parameters. Isolate that draw so that swapping
        # this head cannot change initialization of the other networks in a fit.
        with torch.random.fork_rng(devices=[]):
            self.query = nn.Linear(dim, width, bias=False, device='cpu', dtype=query_weight.dtype)
            self.key = nn.Linear(dim, width, bias=False, device='cpu', dtype=key_weight.dtype)
        generator = torch.Generator(device='cpu').manual_seed(seed)
        with torch.no_grad():
            self.query.weight[:dim].copy_(query_weight.detach().cpu())
            self.key.weight[:dim].copy_(key_weight.detach().cpu())
            self.query.weight[dim:].normal_(std=0.01 / dim**0.5, generator=generator)
            self.key.weight[dim:].zero_()
        self.scale = base_head.scale
        self.to(key_weight.device)

    def score(self, query, keys):
        projected = self.query(query).unsqueeze(1)
        return torch.bmm(projected, keys.transpose(1, 2)).squeeze(1) * self.scale
