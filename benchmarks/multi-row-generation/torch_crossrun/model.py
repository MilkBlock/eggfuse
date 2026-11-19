"""Standalone PyTorch implementation of the two-Run Cell decoder."""
import json
import math
from pathlib import Path

import torch
from torch import nn


DIM = 64
KEYS = 8
VALUES = 4
INPUT_ROWS = 4
OUTPUT_SLOTS = 8
FIELD_WIDTHS = (KEYS, VALUES, VALUES)
TOKEN_WIDTH = DIM + 2 + 2 * INPUT_ROWS + sum(FIELD_WIDTHS)


def projection_recipe(path):
    """Resolve the compiler's atom numbering to each stage's tensor input order."""
    plan = json.loads(Path(path).read_text())
    if plan.get('schema') != 'eggfuse.crossrun.direct-input-projection/v1':
        raise ValueError('unsupported compiler projection schema')
    stages = []
    for name, tables, widths, result in (
            ('make', ('A', 'B'), (3, 3), 'Pair'),
            ('finish', ('Pair', 'Request'), (5, 3), 'Result')):
        rule = plan['rules'][name]
        inputs = rule['inputs']
        if (len(inputs) != 2 or set(inputs) != set(tables) or rule['output_table'] != result
                or len(rule['outputs']) != 5):
            raise ValueError(f'unsupported {name} rule interface')
        routes = []
        for atom, column in rule['outputs']:
            if type(atom) is not int or atom not in (0, 1):
                raise ValueError(f'invalid {name} projection atom')
            side = tables.index(inputs[atom])
            if type(column) is not int or not 0 <= column < widths[side]:
                raise ValueError(f'invalid {name} input column')
            routes.append((side, column))
        stages.append(tuple(routes))
    return tuple(stages)


def symbols(indices, width, dtype):
    classes = torch.arange(width, device=indices.device)
    return (indices.unsqueeze(-1) == classes).to(dtype)


def hard_symbol(logits):
    soft = logits.softmax(dim=-1)
    hard = symbols(logits.argmax(dim=-1), logits.shape[-1], logits.dtype)
    return hard + (soft - soft.detach())


def make_token(hidden, active, left, right, fields):
    heads = (active, left, right, *fields.split(FIELD_WIDTHS, dim=-1))
    return torch.cat([hidden, *(hard_symbol(head) for head in heads)], dim=-1)


def project(left_rows, right_rows, left_scores, right_scores, routes):
    """Gather only columns of the two rows chosen by the learned pointer heads."""
    chosen = []
    for rows, scores in ((left_rows, left_scores), (right_rows, right_scores)):
        index = scores.argmax(dim=-1, keepdim=True).expand(-1, -1, rows.shape[-1])
        chosen.append(rows.gather(1, index))
    return torch.stack([chosen[side][..., column] for side, column in routes], dim=-1)


def as_field_logits(rows, dtype):
    return torch.cat([symbols(column, width, dtype)
                      for column, width in zip(rows[..., 2:].unbind(-1), FIELD_WIDTHS)], dim=-1)


def field_ids(logits):
    return torch.stack([group.argmax(dim=-1) for group in logits.split(FIELD_WIDTHS, dim=-1)], dim=-1)


class FeedForward(nn.Module):
    def __init__(self, input_width, hidden_width, output_width):
        super().__init__()
        self.layers = nn.Sequential(nn.Linear(input_width, hidden_width), nn.GELU(),
                                    nn.Linear(hidden_width, output_width))

    def forward(self, x):
        return self.layers(x)


class Attention(nn.Module):
    def __init__(self):
        super().__init__()
        self.q = nn.Linear(DIM, DIM, bias=False)
        self.k = nn.Linear(DIM, DIM, bias=False)
        self.v = nn.Linear(DIM, DIM, bias=False)
        self.pq = nn.Linear(DIM, 32, bias=False)
        self.pk = nn.Linear(DIM, 32, bias=False)
        self.position_scale = nn.Parameter(torch.tensor(0.1))
        self.register_buffer('frequencies', torch.exp(-math.log(10000) * torch.arange(8) / 8), persistent=False)

    def rotate(self, x, positions):
        axes = []
        for axis, part in enumerate(x.split(16, dim=-1)):
            theta = positions[:, axis, None].to(x.dtype) * self.frequencies
            cos, sin = torch.cos(theta), torch.sin(theta)
            even, odd = part[..., ::2], part[..., 1::2]
            axes.append(torch.stack((cos * even - sin * odd, sin * even + cos * odd), -1).flatten(-2))
        return torch.cat(axes, dim=-1)

    def prepare(self, memory, positions):
        return self.k(memory), self.v(memory), self.rotate(self.pk(memory), positions)

    def read(self, query, positions, memory):
        key, value, position_key = memory
        scores = self.q(query) @ key.transpose(-1, -2) / math.sqrt(DIM)
        position_scores = self.rotate(self.pq(query), positions) @ position_key.transpose(-1, -2)
        scores = scores + self.position_scale * position_scores / math.sqrt(32)
        return scores, scores.softmax(dim=-1) @ value

    def forward(self, query, memory, query_positions, memory_positions):
        return self.read(query, query_positions, self.prepare(memory, memory_positions))


class StreamBlock(nn.Module):
    def __init__(self):
        super().__init__()
        self.norm = nn.LayerNorm(DIM)
        self.current = Attention()
        self.source = Attention()
        self.history = Attention()
        self.ff = FeedForward(DIM, 2 * DIM, DIM)

    def forward(self, q, positions, source, history):
        normalized = self.norm(q)
        q = q + self.current(normalized, normalized, positions, positions)[1]
        q = q + self.source.read(self.norm(q), positions, source)[1]
        if history is not None:
            q = q + self.history.read(self.norm(q), positions, history)[1]
        return q + self.ff(self.norm(q))


class Make(nn.Module):
    def __init__(self):
        super().__init__()
        self.encoder = FeedForward(KEYS + VALUES + 2, DIM, DIM)
        self.row = nn.Embedding(4, DIM)
        self.position = nn.Embedding(4, DIM)
        self.blocks = nn.ModuleList([StreamBlock() for _ in range(3)])
        self.history_encoder = nn.Linear(TOKEN_WIDTH, DIM)
        self.norm = nn.LayerNorm(DIM)
        self.left = Attention()
        self.right = Attention()
        self.active = nn.Linear(DIM, 2)
        self.fields = FeedForward(DIM, 2 * DIM, sum(FIELD_WIDTHS))

    def forward(self, x, rows, source_positions, pair_positions, routes, static):
        source = self.encoder(x)
        memory = [block.source.prepare(source, source_positions) for block in self.blocks]
        left_memory = self.left.prepare(source[:, :INPUT_ROWS], source_positions[:INPUT_ROWS])
        right_memory = self.right.prepare(source[:, INPUT_ROWS:], source_positions[INPUT_ROWS:])
        history = [None] * len(self.blocks)
        generated = []
        for t in range(2):
            pos = pair_positions[t::2]
            q = self.row(pos[:, 0]) + self.position.weight[t]
            q = q.unsqueeze(0).expand(x.shape[0], -1, -1)
            for block, source_kv, generated_kv in zip(self.blocks, memory, history):
                q = block(q, pos, source_kv, generated_kv)
            hidden = self.norm(q)
            left = self.left.read(hidden, pos, left_memory)[0]
            right = self.right.read(hidden, pos, right_memory)[0]
            active = self.active(hidden)
            if static:
                fields = as_field_logits(project(*rows, left, right, routes), hidden.dtype)
            else:
                fields = self.fields(hidden)
            emitted = make_token(hidden, active, left, right, fields)
            generated.append((hidden, active, left, right, fields, emitted))
            if t == 0:
                encoded = self.history_encoder(emitted)
                history = [block.history.prepare(block.norm(encoded), pos) for block in self.blocks]
        return tuple(torch.stack(group, dim=2).flatten(1, 2) for group in zip(*generated))


class Finish(nn.Module):
    def __init__(self):
        super().__init__()
        self.pair = nn.Linear(TOKEN_WIDTH, DIM)
        self.request = nn.Linear(2 * INPUT_ROWS + VALUES, DIM)
        self.slot = nn.Embedding(OUTPUT_SLOTS, DIM)
        self.read = Attention()
        self.mix = Attention()
        self.left = Attention()
        self.right = Attention()
        self.norm = nn.LayerNorm(DIM)
        self.ff = FeedForward(DIM, 2 * DIM, DIM)
        self.active = nn.Linear(DIM, 2)
        self.fields = nn.Linear(DIM, sum(FIELD_WIDTHS))
        keep = torch.ones(TOKEN_WIDTH)
        keep[66:74] = 0
        self.register_buffer('hide_parents', keep, persistent=False)
        keep = keep.clone()
        keep[:DIM] = 0
        self.register_buffer('hide_parents_and_latent', keep, persistent=False)

    def forward(self, emitted, requests, pp, rp, op, routes, static, mask):
        if mask == 'parents':
            visible = emitted * self.hide_parents
        elif mask == 'parents_latent':
            visible = emitted * self.hide_parents_and_latent
        elif mask == 'none':
            visible = emitted
        else:
            raise ValueError(f'unsupported mask: {mask}')
        pair = self.pair(visible)
        encoded = torch.cat([symbols(col, width, emitted.dtype)
                             for col, width in zip(requests.unbind(-1), (INPUT_ROWS, INPUT_ROWS, VALUES))], -1)
        demand = self.request(encoded)
        q = self.slot.weight.unsqueeze(0).expand_as(pair)
        mixed = self.read(q, torch.cat([pair, demand], dim=1), op, torch.cat([pp, rp]))[1]
        q = self.norm(q + mixed)
        mixed = q + self.mix(q, q, op, op)[1]
        hidden = self.norm(mixed + self.ff(mixed))
        left = self.left(hidden, pair, op, pp)[0]
        right = self.right(hidden, demand, op, rp)[0]
        if static:
            parts = visible[..., 66:].split((INPUT_ROWS, INPUT_ROWS, *FIELD_WIDTHS), -1)
            columns = torch.stack([part.argmax(dim=-1) for part in parts], -1)
            fields = as_field_logits(project(columns, requests, left, right, routes), hidden.dtype)
        else:
            fields = self.fields(hidden)
        return hidden, self.active(hidden), left, right, fields


class CrossRun(nn.Module):
    def __init__(self, arm, plan_path):
        super().__init__()
        if arm not in ('learned', 'static', 'aux'):
            raise ValueError(f'unsupported arm: {arm}')
        self.arm = arm
        self.make_routes, self.finish_routes = projection_recipe(plan_path)
        self.make = Make()
        self.finish = Finish()
        ids = torch.arange(OUTPUT_SLOTS)
        positions = torch.stack([ids // 2, ids % 2], dim=-1)
        self.register_buffer('instance_ids', ids[:INPUT_ROWS].view(1, INPUT_ROWS, 1), persistent=False)
        self.register_buffer('table_tags', torch.eye(2), persistent=False)
        self.register_buffer('source_positions', positions, persistent=False)
        self.register_buffer('pair_positions', positions + torch.tensor([0, 2]), persistent=False)
        self.register_buffer('request_positions', positions[:4] + torch.tensor([0, 4]), persistent=False)
        self.register_buffer('result_positions', positions + torch.tensor([0, 6]), persistent=False)

    def forward(self, a, b, requests, mask='none', training_heads=False):
        """Inputs have shapes [B,4,2], [B,4,2], [B,4,3], already on the model device."""
        if (a.ndim != 3 or tuple(a.shape[1:]) != (4, 2) or b.shape != a.shape
                or requests.shape != (a.shape[0], 4, 3)):
            raise ValueError('expected A[B,4,2], B[B,4,2], Request[B,4,3]')
        ids = self.instance_ids.expand(a.shape[0], -1, -1)
        raw = []
        encoded = []
        dtype = self.make.row.weight.dtype
        for kind, rows in enumerate((a, b)):
            raw.append(torch.cat([ids, rows], dim=-1))
            tag = self.table_tags[kind].expand(a.shape[0], INPUT_ROWS, -1)
            encoded.append(torch.cat([symbols(rows[..., 0], KEYS, dtype),
                                      symbols(rows[..., 1], VALUES, dtype), tag], -1))
        static = self.arm != 'learned'
        h1, active1, left1, right1, fields1, pair_token = self.make(
            torch.cat(encoded, dim=1), raw, self.source_positions, self.pair_positions, self.make_routes, static)
        h2, active2, left2, right2, fields2 = self.finish(
            pair_token, requests, self.pair_positions, self.request_positions,
            self.result_positions, self.finish_routes, static, mask)
        if self.arm == 'aux' and training_heads:
            fields1, fields2 = self.make.fields(h1), self.finish.fields(h2)
        return [(active1, left1, right1, fields1), (active2, left2, right2, fields2)], pair_token


def decode(outputs):
    return [dict(active=active.argmax(dim=-1),
                 pointers=torch.stack([left.argmax(dim=-1), right.argmax(dim=-1)], dim=-1),
                 fields=field_ids(fields)) for active, left, right, fields in outputs]
