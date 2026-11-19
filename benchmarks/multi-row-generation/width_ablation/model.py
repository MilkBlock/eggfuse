"""Frozen Figure 20 policy unfolded into R causal rows, eight slots in total."""
from contextlib import contextmanager
from contextvars import ContextVar
import importlib.util
import math
from pathlib import Path
import sys

import torch
from torch import nn
import torch.nn.functional as F


HERE = Path(__file__).resolve().parent
FIG20 = HERE.parent / 'eclass_ablation'
sys.path.append(str(FIG20))
# The original benchmark also names its module model.py. Load it under a
# distinct name so callers and tools can use both implementations in one process.
_spec = importlib.util.spec_from_file_location('width_ablation_figure20', FIG20 / 'model.py')
_fig20 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fig20)
AliasSystem, BASE, INPUTS = _fig20.AliasSystem, _fig20.BASE, _fig20.INPUTS
from decoder import OneRowDecoder, MAX_CANDIDATES


SCHEDULES = ('parallel', 'serial_lanes', 'zero_history')
_layout = ContextVar('eggfuse_width_execution', default=(1, 'parallel'))
_finish_layout = ContextVar('eggfuse_finish_width_execution', default=(1, 'parallel'))


@contextmanager
def execution_layout(rows, schedule):
    if isinstance(rows, tuple) and len(rows) == 2:
        make_rows, finish_rows = rows
    else:
        make_rows = finish_rows = rows
    if make_rows not in (1, 2, 4) or finish_rows not in (1, 2, 4) or schedule not in SCHEDULES:
        raise ValueError('use 1, 2 or 4 rows per Run and a supported schedule')
    make_handle = _layout.set((make_rows, schedule))
    finish_handle = _finish_layout.set((finish_rows, schedule))
    try:
        yield
    finally:
        _finish_layout.reset(finish_handle)
        _layout.reset(make_handle)


class CoordinateMap(nn.Module):
    """Four fixed features of a packed physical address, one map shared across rows."""

    def __init__(self, dim):
        super().__init__()
        ids = torch.arange(MAX_CANDIDATES, dtype=torch.float32)
        angle = ids * (2 * math.pi / MAX_CANDIDATES)
        features = torch.stack((torch.ones_like(ids), 2*ids/(MAX_CANDIDATES-1)-1,
                                angle.sin(), angle.cos()), dim=-1)
        self.register_buffer('features', features, persistent=False)
        self.projection = nn.Linear(4, dim, bias=False)

    @property
    def weight(self):
        # Compatibility with the parent's packed address reads. This evaluates
        # one low-dimensional function over the eight fixed addresses.
        return self.projection(self.features)



def _select(rows, pointer):
    return rows.gather(1, pointer.unsqueeze(-1).expand(-1, -1, rows.shape[-1]))


def _decision(decoder, scores, code_width):
    pointer = scores.argmax(-1)
    code = (pointer.unsqueeze(-1) == decoder.addresses[:scores.shape[-1]]).to(scores.dtype)
    if decoder.training:
        probability = scores.softmax(-1)
        code = code + (probability - probability.detach())
    return pointer, F.pad(code, (0, code_width - scores.shape[-1]))


def grouped_stage(decoder, left, right, left_features, right_features, ports, routes,
                  rule_id, history, *, rows, schedule):
    """One round emits one position in every lane. Keys/pool are shared within a stage."""
    if decoder.slots != 8 or rows not in (1, 2, 4) or schedule not in SCHEDULES:
        raise ValueError('expected eight output slots in a supported layout')
    if not 0 <= rule_id < decoder.num_rules:
        raise ValueError('rule index outside declared vocabulary')
    length = decoder.slots // rows
    head = decoder.heads[0 if decoder.shared_heads else rule_id]
    left_keys = head.key(left_features).transpose(1, 2)
    right_keys = head.key(right_features).transpose(1, 2)
    projection, constants = decoder._routes(left, right, routes)
    context = decoder.pool(torch.cat((left_features.mean(1), right_features.mean(1),
                                      ports[:, 0], ports[:, 1]), dim=-1))
    base = context[:, None, None] + decoder.position.weight.reshape(rows, length, decoder.dim)
    left_port, right_port = ports[:, 0:1], ports[:, 1:2]

    def execute_lanes(first_row, stop_row):
        lane_count = stop_row - first_row
        previous = context.new_zeros((context.shape[0], lane_count, decoder.token_width))
        columns = []
        for position in range(length):
            consumed = previous if history and schedule != 'zero_history' else torch.zeros_like(previous)
            hidden = torch.tanh(base[:, first_row:stop_row, position] + decoder.history(consumed))
            active = decoder.active(hidden)
            left_logits = torch.bmm(head.query(hidden + left_port), left_keys) * head.scale
            li, lc = _decision(decoder, left_logits, MAX_CANDIDATES)
            chosen = _select(left_features, li)
            query = hidden + right_port + decoder.condition_right(chosen)
            right_logits = torch.bmm(head.query(query), right_keys) * head.scale
            ri, rc = _decision(decoder, right_logits, MAX_CANDIDATES)
            _, ac = _decision(decoder, active, 2)
            selected = torch.cat((_select(left, li), _select(right, ri)), dim=-1)
            if constants is not None:
                selected = torch.cat((selected, constants[:, None].expand(-1, lane_count, -1)), dim=-1)
            payload = selected.index_select(-1, projection)
            padded = F.pad(payload.to(hidden.dtype), (0, decoder.max_columns - payload.shape[-1]))
            previous = torch.cat((hidden, ac, lc, rc, padded), dim=-1)
            columns.append((hidden, active, left_logits, right_logits, payload, previous))
        # [batch, row, position, ...] -> [batch, packed address, ...]
        return tuple(torch.stack(column, dim=2).flatten(1, 2) for column in zip(*columns))

    if schedule == 'serial_lanes' and rows > 1:
        per_lane = [execute_lanes(r, r + 1) for r in range(rows)]
        tensors = tuple(torch.cat(column, dim=1) for column in zip(*per_lane))
    else:
        tensors = execute_lanes(0, rows)
    hidden, active, left_logits, right_logits, payload, token = tensors
    stage = dict(hidden=hidden, active_logits=active, left_logits=left_logits,
                 right_logits=right_logits, active=active.argmax(-1),
                 pointers=torch.stack((left_logits.argmax(-1), right_logits.argmax(-1)), dim=-1),
                 rows=payload, fields=payload[..., 2:])
    return stage, token


class WidthDecoder(OneRowDecoder):
    def __init__(self, original):
        nn.Module.__init__(self)
        for key in ('dim', 'num_rules', 'shared_heads', 'slots', 'max_columns', 'payload_offset', 'token_width'):
            setattr(self, key, getattr(original, key))
        for key, buffer in original.named_buffers(recurse=False):
            self.register_buffer(key, buffer, persistent=False)
        for key, module in original.named_children():
            if key not in ('position', 'source_position'):
                self.add_module(key, module)
        self.position = CoordinateMap(self.dim)
        self.source_position = CoordinateMap(self.dim)

    def _stage(self, *args):
        rows, schedule = _layout.get()
        return grouped_stage(self, *args, rows=rows, schedule=schedule)


class WidthSystem(AliasSystem):
    def __init__(self, schema, seed):
        super().__init__(schema, seed)
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(seed + 103)
            self.decoder = WidthDecoder(self.decoder)

    def load_fig20(self, state):
        """Optional diagnostic: copy common weights and retain the new coordinate functions."""
        current = self.state_dict()
        old_keys = {'decoder.position.weight', 'decoder.source_position.weight'}
        new_keys = {'decoder.position.projection.weight', 'decoder.source_position.projection.weight'}
        if set(state) - old_keys != set(current) - new_keys or not old_keys <= set(state):
            raise ValueError('checkpoint has a different architecture from Figure 20')
        for key in set(current) - new_keys:
            current[key] = state[key]
        self.load_state_dict(current, strict=True)

    def forward(self, *inputs, rows=1, schedule='parallel'):
        with execution_layout(rows, schedule):
            return super().forward(*inputs)

    def resume(self, *inputs, rows=None, schedule='parallel'):
        if rows is None:
            rows, schedule = _finish_layout.get()
        with execution_layout(rows, schedule):
            return super().resume(*inputs)
