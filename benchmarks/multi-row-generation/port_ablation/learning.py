"""Set supervision and frozen static-encoder alternatives."""

import hashlib
import sys
from pathlib import Path

import numpy as np
import torch
from torch import nn
import torch.nn.functional as F

HERE = Path(__file__).resolve().parent
sys.path.append(str(HERE.parent / "allocation"))
from assignment import assign
from decoder import OneRowDecoder
from encoders import TemplateEncoder

ARMS = ("private_roles", "shared_roles", "shared_id", "shared_pooled", "shared_ports")
WIDTH = 32


def state_digest(state):
    h = hashlib.sha256()
    for name, tensor in sorted(state.items()):
        h.update(name.encode())
        h.update(tensor.detach().cpu().contiguous().numpy().tobytes())
    return h.hexdigest()


class System(nn.Module):
    def __init__(self, schema, rule_count, arm, columns, value_classes, seed):
        super().__init__()
        sharing, variant = arm.split("_")
        torch.manual_seed(seed)
        self.decoder = OneRowDecoder(WIDTH, rule_count, sharing != "private", max_columns=columns)
        torch.manual_seed(seed + 17)
        self.encoder = TemplateEncoder(schema, WIDTH, variant)
        # Same initialization of the readouts, independent of encoder parameter count.
        torch.manual_seed(seed + 31)
        self.aux = nn.ModuleList([nn.Linear(WIDTH, columns * value_classes) for _ in range(2)])
        self.base_head_digest = state_digest(self.decoder.heads[0].state_dict())
        if sharing == "wide":
            from capacity import WideSharedPointerHead

            self.decoder.heads[0] = WideSharedPointerHead(
                self.decoder.heads[0], rule_count, seed=seed
            )
        self.columns = columns
        self.value_classes = value_classes

    def infer(self, inputs, static, conditions):
        return self.decoder(*inputs, conditions, *static)

    def initial_digests(self):
        dec = {k: v for k, v in self.decoder.state_dict().items() if not k.startswith("heads.")}
        heads = [state_digest(h.state_dict()) for h in self.decoder.heads]
        if len(set(heads)) != 1:
            raise RuntimeError("private initial heads differ")
        return dict(
            common=state_digest(dec),
            head=self.base_head_digest,
            aux=state_digest(self.aux.state_dict()),
            encoder=state_digest(self.encoder.state_dict()),
        )


def align_one(stage, target):
    live = target[..., 0]
    batch, slots = live.shape
    cost = np.zeros((batch, slots, slots), dtype=np.float64)
    for col, key in enumerate(("active_logits", "left_logits", "right_logits")):
        x = stage[key].detach().cpu().numpy()
        maximum = x.max(-1, keepdims=True)
        nll = maximum + np.log(np.exp(x - maximum).sum(-1, keepdims=True)) - x
        selected = np.take_along_axis(nll[:, :, None, :], target[:, None, :, col, None], -1)[..., 0]
        cost += selected if col == 0 else selected * live[:, None, :]
    return assign(cost)


def align(stages, first, second):
    batch = np.arange(len(first))[:, None]
    mapping = align_one(stages[0], first)
    first = first[batch, mapping]
    # second's source-parent label names the original unordered target1 slot.
    # For loss only, map it to the physical output slot assigned to that label.
    second = second.copy()
    second[..., 1] = np.argsort(mapping, axis=1)[batch, second[..., 1]]
    return first, second[batch, align_one(stages[1], second)]


def per_slot(scores, y):
    return F.cross_entropy(scores.flatten(0, 1), y.flatten(), reduction="none").reshape_as(y)


def objective(system, stages, targets, value_min):
    total = stages[0]["active_logits"].new_zeros(())
    for stage, y, head in zip(stages, targets, system.aux):
        live = y[..., 0]
        total = total + per_slot(stage["active_logits"], live).mean()
        for i, key in enumerate(("left_logits", "right_logits"), 1):
            total = total + (per_slot(stage[key], y[..., i]) * live).mean()
        width = y.shape[-1] - 3
        pred = head(stage["hidden"]).unflatten(-1, (system.columns, system.value_classes))[
            ..., :width, :
        ]
        # Average across actual projected columns, ensuring templates with wider payloads
        # do not silently receive higher task weight.
        aux = (
            F.cross_entropy(
                pred.flatten(0, 2), (y[..., 3:] - value_min).flatten(), reduction="none"
            )
            .reshape(*y.shape[:2], width)
            .mean(-1)
        )
        total = total + (aux * live).mean()
    return total
