"""GPU recurrent latent, role-separated rotary references and neural certificate heads.

This module never imports the reference executor or verifier. The only initial
semantic input is the seed vector. No target latent, teacher layout or certificate
is provided between transitions. Integer handles are symbolic roles, not floats.
"""
import numpy as np
import mlx.core as mx
import mlx.nn as nn
from schema import DIM, SPECS, OFFSETS, WIDTH, CATEGORICAL

# Independent axes: Cell rotations occupy the first half, port rotations the second.
FREQ = mx.array(np.exp(-np.log(10000.) * np.arange(DIM // 4) / (DIM // 4)), mx.float32)
BASE = mx.ones((DIM,), mx.float32) / np.sqrt(DIM)


def rotate(x, coordinate, axis, inverse=False):
    start = 0 if axis == 'cell' else DIM // 2
    part = x[..., start:start + DIM // 2]
    angle = coordinate.astype(mx.float32)[..., None] * FREQ * (-1 if inverse else 1)
    c, s = mx.cos(angle), mx.sin(angle)
    even, odd = part[..., 0::2], part[..., 1::2]
    value = mx.stack((c * even - s * odd, s * even + c * odd), axis=-1).reshape(part.shape)
    return mx.concatenate((value, x[..., DIM // 2:]), axis=-1) if start == 0 else mx.concatenate((x[..., :DIM // 2], value), axis=-1)


def address(cell, port):
    shape = mx.broadcast_arrays(cell, port)[0].shape
    key = mx.broadcast_to(BASE, shape + (DIM,))
    return rotate(rotate(key, port, 'port'), cell, 'cell')


def rebase(key, old_cell, old_port, new_cell, new_port):
    local = rotate(rotate(key, old_cell, 'cell', True), old_port, 'port', True)
    return rotate(rotate(local, new_port, 'port'), new_cell, 'cell')


def fields(logits):
    return {k: logits[..., a:b].reshape(logits.shape[:-1] + SPECS[k]) for k, (a, b) in OFFSETS.items()}


def discrete(logits):
    return {k: mx.stop_gradient(mx.argmax(v, axis=-1)) if k in CATEGORICAL else mx.stop_gradient((v >= 0).astype(mx.int32)) for k, v in fields(logits).items()}


class CellNet(nn.Module):
    def __init__(self):
        super().__init__()
        # pre-existing Eq, SameValue receipt, requested free result port, 8-bit annotation.
        self.encoder = nn.Sequential(nn.Linear(15, 192), nn.GELU(), nn.Linear(192, DIM), nn.Tanh())
        self.transition_net = nn.Sequential(nn.Linear(DIM + 3, 256), nn.GELU(), nn.Linear(256, DIM), nn.Tanh())
        self.decoder = nn.Linear(DIM, WIDTH)

    def advance(self, token, owner_position, phase, positions):
        local = rotate(token, owner_position, 'cell', True)
        request = mx.broadcast_to(mx.eye(3)[phase], (len(token), 3))
        # The old latent itself is the input, never decoded and re-encoded fields.
        local = local + self.transition_net(mx.concatenate((local, request), axis=-1))
        logits = self.decoder(local)
        owner = discrete(logits)['owner'][:, 0]
        position = mx.take_along_axis(positions, owner[:, None], axis=1)[:, 0]
        return rotate(local, position, 'cell'), position, logits, owner

    def rollout(self, seed, positions, old_payload_mode='keep'):
        token = rotate(self.encoder(seed), positions[:, 0], 'cell')
        position = positions[:, 0]
        tokens, logits, owners, locations = [], [], [], []
        for phase in range(3):
            token, position, scores, owner = self.advance(token, position, phase, positions)
            tokens.append(token); logits.append(scores); owners.append(owner); locations.append(position)
        reads = self.read_old(tokens[2], locations[2], owners[2], tokens[1], positions, old_payload_mode)
        return dict(tokens=mx.stack(tokens), logits=mx.stack(logits), owners=mx.stack(owners),
                    locations=mx.stack(locations), **reads)

    def read_old(self, final, final_position, owner, old, positions, mode, query_ports=None):
        current = discrete(self.decoder(rotate(final, final_position, 'cell', True)))
        retired = current['retired'][:, 0] != 0
        # The old A token is a decoy after transfer. Its bytes may be arbitrary or NaN.
        if mode == 'zero': old = mx.zeros_like(old)
        elif mode == 'nan': old = mx.full_like(old, float('nan'))
        elif mode == 'random': old = mx.sin(mx.arange(old.size).reshape(old.shape).astype(mx.float32)) * 100
        elif mode != 'keep': raise ValueError('old payload mode')
        # Without transfer, the same A address receives its newest generated latent.
        current_a = mx.where((owner == 1)[:, None], final, old)
        bank = mx.stack((current_a, final), axis=1)
        active = mx.stack((~retired, owner == 2), axis=1)
        # Mask before any arithmetic; multiplying an inactive NaN by zero is unsafe.
        bank = mx.where(active[..., None], bank, 0)
        picked = mx.take_along_axis(bank, mx.clip(owner - 1, 0, 1)[:, None, None], axis=1)[:, 0]
        bank_index = mx.clip(owner - 1, 0, 1)
        bank_positions = positions[:, 1:3]
        selected_position = mx.take_along_axis(bank_positions, bank_index[:, None], axis=1)[:, 0]
        h = rotate(picked, selected_position, 'cell', True)
        header = discrete(self.decoder(h))
        ports = mx.broadcast_to(mx.arange(4), (len(final), 4))
        original = address(positions[:, 1, None], ports if query_ports is None else query_ports)
        candidates = address(positions[:, 1, None], ports)
        selected_port = mx.stop_gradient(mx.argmax(original @ mx.swapaxes(candidates, -1, -2), axis=-1))
        # Both owner and port projection come from the generated latent's decoder.
        mapped = mx.take_along_axis(header['alias'], selected_port, axis=1)
        translated = rebase(original, positions[:, 1, None], selected_port, selected_position[:, None], mapped)
        slots = mx.broadcast_to(mx.arange(5), (len(final), 5))
        target_keys = address(selected_position[:, None], slots)
        resolved = mx.stop_gradient(mx.argmax(translated @ mx.swapaxes(target_keys, -1, -2), axis=-1))
        roles = mx.take_along_axis(header['layout'], resolved, axis=1)
        return dict(read_roles=roles, read_ports=resolved, read_payload=header['payload'], read_eq=header['eq'],
                    read_valid=mx.take_along_axis(active, bank_index[:, None], axis=1)[:, 0] & (owner > 0) & mx.all(mapped < 5, axis=1),
                    rebased_keys=translated, direct_keys=address(selected_position[:, None], mapped),
                    active_bank=active, active_bank_contents=bank, read_logits=self.decoder(h))


def loss(model, seed, positions, targets):
    result = model.rollout(seed, positions)
    total = mx.array(0.)
    weights = {'layout': 2., 'alias': 2., 'eq': 2., 'payload': 2.}
    for k, v in fields(result['logits']).items():
        target = targets[k]
        if k in CATEGORICAL:
            part = nn.losses.cross_entropy(v.reshape(-1, v.shape[-1]), target.reshape(-1), reduction='mean')
        else:
            # Every comparison matters; a small average token MSE is not the objective.
            part = nn.losses.binary_cross_entropy(v, target.astype(mx.float32), reduction='mean')
        total = total + weights.get(k, 1.) * part
    return total
