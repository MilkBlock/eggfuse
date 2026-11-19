"""Load frozen checkpoints and emit the two stages' discrete results."""
import hashlib
import json
from pathlib import Path

import mlx.core as mx

from .compiler import projection_recipe
from .model import CrossRun, decode

ARMS = ('learned', 'static', 'aux')
MASKS = ('none', 'parents', 'parents_latent')


def load_model(checkpoint_directory, plan_path):
    """Load model.safetensors and its fit.json metadata, binding plan and weights by hash."""
    directory = Path(checkpoint_directory)
    meta = json.loads((directory / 'fit.json').read_text())
    weights = directory / 'model.safetensors'
    if hashlib.sha256(weights.read_bytes()).hexdigest() != meta['model_sha256']:
        raise ValueError('model.safetensors differs from the checkpoint metadata')
    if hashlib.sha256(Path(plan_path).read_bytes()).hexdigest() != meta['plan_sha256']:
        raise ValueError('plan file differs from the one recorded for this checkpoint')
    if meta['arm'] not in ARMS:
        raise ValueError(f"unknown checkpoint arm {meta['arm']!r}")
    model = CrossRun(meta['arm'], projection_recipe(plan_path))
    model.load_weights(str(weights))
    model.eval()
    return model


def _table(value, width, name):
    value = mx.array(value)
    if value.dtype not in (mx.int8, mx.uint8, mx.int16, mx.uint16, mx.int32, mx.uint32, mx.int64, mx.uint64):
        raise ValueError(f'{name} requires integer columns')
    if value.shape == (4, width):
        value = value[None, ...]
    if value.ndim != 3 or value.shape[1:] != (4, width):
        raise ValueError(f'{name} requires shape (batch, 4, {width}) or (4, {width})')
    return value.astype(mx.int32)


def infer(model, a, b, requests, mask='none'):
    """Run both stages on batched integer tables. Returns (decoded_stages, Pair tokens).

    Each A/B row is [key, value], with key 0..7 and value 0..3. Source record
    identity is its position 0..3. Each Request is [A identity, B identity, tag],
    all in 0..3. The returned MLX arrays retain their batch dimension.
    """
    if mask not in MASKS:
        raise ValueError(f'unsupported parent visibility {mask!r}')
    a = _table(a, 2, 'A')
    b = _table(b, 2, 'B')
    requests = _table(requests, 3, 'Request')
    if not (a.shape[0] == b.shape[0] == requests.shape[0]):
        raise ValueError('all tables must have the same batch size')
    with mx.stream(mx.gpu):
        if not mx.metal.is_available():
            raise RuntimeError('EggFuse inference requires a Metal GPU')
        outputs, emitted = model(a, b, requests, mask=mask)
        return decode(outputs), emitted
