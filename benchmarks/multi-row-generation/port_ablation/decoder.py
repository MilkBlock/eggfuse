"""One-row autoregressive PyTorch decoder for two consecutive Cell rules.

A slot predicts active/null and two source addresses. Source rows include all
physical columns named by the compiler route (including IDs, when present).
The token contains a recurrent latent, the three hard decisions and the actual
gathered integer payload. The measured fixtures use integers represented exactly
in FP32. The next slot reads that token; finish receives only the make frontier
and the incoming demand table. Neither stage receives labels or a legal-pair mask.
"""
import copy
import math

import torch
from torch import nn
import torch.nn.functional as F


MAX_CANDIDATES = 8


class PointerHead(nn.Module):
    """A single scorer serves both operand roles; the port embedding supplies its role."""

    def __init__(self, width):
        super().__init__()
        self.key = nn.Linear(width, width, bias=False)
        self.query = nn.Linear(width, width, bias=False)
        self.scale = 1 / math.sqrt(width)

    def score(self, query, keys):
        return torch.bmm(self.query(query).unsqueeze(1), keys.transpose(1, 2)).squeeze(1) * self.scale


class OneRowDecoder(nn.Module):
    """Same stage and recurrent parameters in both arms; only PointerHead is tied/copied."""

    def __init__(self, dim, num_rules, shared_heads, max_columns=8, slots=8):
        super().__init__()
        if not 1 <= slots <= MAX_CANDIDATES or num_rules < 1 or max_columns < 1:
            raise ValueError('need 1..8 output slots, at least one rule and positive row width')
        self.dim = dim
        self.num_rules = num_rules
        self.shared_heads = shared_heads
        self.slots = slots
        self.max_columns = max_columns
        self.payload_offset = dim + 2 + 2 * MAX_CANDIDATES
        self.token_width = self.payload_offset + max_columns
        self.register_buffer('addresses', torch.arange(MAX_CANDIDATES), persistent=False)
        self.register_buffer('symbols', torch.arange(16), persistent=False)
        # Known small scalar values have a categorical coordinate. The numerical
        # channel also accepts other small signed integer literals/identities.
        self.input_row = nn.Linear(max_columns * 18, dim)
        self.source_position = nn.Embedding(MAX_CANDIDATES, dim)
        self.position = nn.Embedding(slots, dim)
        self.pool = nn.Linear(dim * 4, dim)
        self.history = nn.Linear(self.token_width, dim, bias=False)
        self.frontier = nn.Linear(self.token_width, dim)
        self.condition_right = nn.Linear(dim, dim, bias=False)
        self.active = nn.Linear(dim, 2)
        initial_head = PointerHead(dim)
        copies = 0 if shared_heads else num_rules - 1
        self.heads = nn.ModuleList([initial_head, *(copy.deepcopy(initial_head) for _ in range(copies))])

    def _source(self, rows):
        width = rows.shape[-1]
        if not (1 <= width <= self.max_columns and 1 <= rows.shape[1] <= MAX_CANDIDATES):
            raise ValueError('input rows exceed the configured column or candidate capacity')
        values = rows.to(self.input_row.weight.dtype)
        categorical = (rows.unsqueeze(-1) == self.symbols).to(values.dtype)
        numeric = torch.sign(values) * torch.log1p(values.abs())
        features = torch.cat((categorical, numeric.unsqueeze(-1), torch.ones_like(values).unsqueeze(-1)), dim=-1)
        padded = F.pad(features.flatten(-2), (0, (self.max_columns - width) * 18))
        return self.input_row(padded) + self.source_position.weight[:rows.shape[1]]

    @staticmethod
    def _select(rows, index):
        return rows.gather(1, index[:, None, None].expand(-1, 1, rows.shape[-1])).squeeze(1)

    def _decision(self, logits, width):
        index = logits.argmax(dim=-1)
        hard = (index[:, None] == self.addresses[:logits.shape[-1]]).to(logits.dtype)
        if self.training:
            soft = logits.softmax(dim=-1)
            hard = hard + (soft - soft.detach())
        return index, F.pad(hard, (0, width - logits.shape[-1]))

    def _routes(self, left, right, routes):
        """Resolve the frozen ordered RHS column copies against the two source widths."""
        if not 1 <= len(routes) <= self.max_columns:
            raise ValueError('output width exceeds the configured column capacity')
        widths = (left.shape[-1], right.shape[-1])
        columns, literals = [], []
        for side, column in routes:
            if side == 2:
                if type(column) is not int or abs(column) > 2**24:
                    raise ValueError('literal must be an FP32-exact small integer')
                columns.append(sum(widths) + len(literals))
                literals.append(column)
                continue
            if side not in (0, 1) or not 0 <= column < widths[side]:
                raise ValueError('invalid source column in projection recipe')
            columns.append(column + (widths[0] if side else 0))
        constants = left.new_tensor(literals).expand(left.shape[0], -1) if literals else None
        return torch.tensor(columns, device=left.device, dtype=torch.long), constants

    def _stage(self, left, right, left_features, right_features, ports, routes, rule_id, history):
        if not 0 <= rule_id < self.num_rules:
            raise ValueError('rule index outside the declared vocabulary')
        head = self.heads[0 if self.shared_heads else rule_id]
        left_keys, right_keys = head.key(left_features), head.key(right_features)
        wire, constants = self._routes(left, right, routes)
        context = self.pool(torch.cat((left_features.mean(1), right_features.mean(1),
                                       ports[:, 0], ports[:, 1]), dim=-1))
        base = context[:, None] + self.position.weight
        previous = context.new_zeros((context.shape[0], self.token_width))
        hidden_rows, emitted, scores, payloads = [], [], [], []
        for position in range(self.slots):
            consumed = previous if history else torch.zeros_like(previous)
            hidden = torch.tanh(base[:, position] + self.history(consumed))
            active = self.active(hidden)
            left_logits = head.score(hidden + ports[:, 0], left_keys)
            li, left_code = self._decision(left_logits, MAX_CANDIDATES)
            # The right query reads its own chosen left source. Equality and
            # visibility remain learned choices; no symbolic match filters here.
            chosen = self._select(left_features, li)
            right_logits = head.score(hidden + ports[:, 1] + self.condition_right(chosen), right_keys)
            ri, right_code = self._decision(right_logits, MAX_CANDIDATES)
            _, active_code = self._decision(active, 2)
            selected = torch.cat((self._select(left, li), self._select(right, ri)), dim=-1)
            if constants is not None:
                selected = torch.cat((selected, constants), dim=-1)
            payload = selected.index_select(-1, wire)
            padded = F.pad(payload.to(hidden.dtype), (0, self.max_columns - payload.shape[-1]))
            previous = torch.cat((hidden, active_code, left_code, right_code, padded), dim=-1)
            emitted.append(previous)
            hidden_rows.append(hidden)
            scores.append((active, left_logits, right_logits))
            payloads.append(payload)
        active, left_logits, right_logits = (torch.stack(items, 1) for items in zip(*scores))
        rows = torch.stack(payloads, dim=1)
        stage = dict(hidden=torch.stack(hidden_rows, dim=1), active_logits=active, left_logits=left_logits,
                     right_logits=right_logits, active=active.argmax(-1),
                     pointers=torch.stack((left_logits.argmax(-1), right_logits.argmax(-1)), dim=-1),
                     rows=rows, fields=rows[..., 2:])
        return stage, torch.stack(emitted, dim=1)

    def finish_from(self, pair_token, requests, finish_ports, pair_width, finish_routes, rule_id, history=True):
        """Resume from the actual retained make tokens plus the next Run's demand rows."""
        if pair_token.shape[1:] != (self.slots, self.token_width):
            raise ValueError('unexpected make frontier shape')
        pair_rows = pair_token[..., self.payload_offset:self.payload_offset + pair_width].to(requests.dtype)
        pair_features = self.frontier(pair_token) + self.source_position.weight[:self.slots]
        return self._stage(pair_rows, requests, pair_features, self._source(requests), finish_ports,
                           finish_routes, rule_id, history)[0]

    def forward(self, a, b, requests, conditions, make_routes, finish_routes, rule_ids, history=True):
        """Execute both rules. ``conditions`` is [batch, two stages, two operand roles, dim]."""
        if conditions.ndim == 3:
            conditions = conditions.unsqueeze(0).expand(a.shape[0], -1, -1, -1)
        if conditions.shape != (a.shape[0], 2, 2, self.dim):
            raise ValueError('expected two stage/operand port vectors per graph')
        make, pair_token = self._stage(a, b, self._source(a), self._source(b), conditions[:, 0],
                                       make_routes, rule_ids[0], history)
        finish = self.finish_from(pair_token, requests, conditions[:, 1], len(make_routes),
                                  finish_routes, rule_ids[1], history)
        return [make, finish], pair_token
