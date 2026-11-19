"""Run both neural stages with PyTorch, from raw source records to emitted tokens."""
import argparse
import hashlib
import json
import os
from pathlib import Path

import torch

from model import CrossRun, decode


# A0 and A1 have identical fields. The first Request refers to A1 specifically.
DEMO = {
    'a': [[3, 1], [3, 1], [5, 2], [7, 0]],
    'b': [[3, 2], [4, 0], [5, 0], [6, 1]],
    'requests': [[1, 0, 2], [2, 2, 1], [3, 1, 0], [0, 3, 3]],
}


def select_device(name):
    uses_mps = name == 'mps' or (name == 'auto' and not torch.cuda.is_available() and torch.backends.mps.is_available())
    if uses_mps and os.environ.get('PYTORCH_ENABLE_MPS_FALLBACK') == '1':
        raise RuntimeError('Unset PYTORCH_ENABLE_MPS_FALLBACK or set it to 0 for GPU execution')
    if name == 'auto':
        if torch.cuda.is_available():
            return torch.device('cuda')
        if torch.backends.mps.is_available():
            return torch.device('mps')
        raise RuntimeError('A GPU is required for auto; --device cpu explicitly selects a reference run')
    if name == 'cuda' and not torch.cuda.is_available():
        raise RuntimeError('CUDA is unavailable')
    if name == 'mps' and not torch.backends.mps.is_available():
        raise RuntimeError('MPS is unavailable')
    return torch.device(name)


def source_tensor(value, sizes, device, name):
    # Only validate the raw input schema. Binding selection is done by CrossRun.
    x = torch.as_tensor(value)
    if x.is_floating_point() or x.dtype == torch.bool or x.is_complex():
        raise ValueError(f'{name} requires integer values')
    if x.ndim == 2:
        x = x.unsqueeze(0)
    if x.ndim != 3 or x.size(1) != 4 or x.size(2) != len(sizes) or x.size(0) == 0:
        raise ValueError(f'{name} must have shape [batch,4,{len(sizes)}] or [4,{len(sizes)}]')
    if torch.any(x < 0) or torch.any(x >= torch.tensor(sizes, device=x.device)):
        raise ValueError(f'{name} columns outside vocabularies {sizes}')
    return x.to(device=device, dtype=torch.long)


@torch.inference_mode()
def predict(model, source, device, mask='none'):
    a = source_tensor(source['a'], (8, 4), device, 'a')
    b = source_tensor(source['b'], (8, 4), device, 'b')
    requests = source_tensor(source['requests'], (4, 4, 4), device, 'requests')
    if a.size(0) != b.size(0) or a.size(0) != requests.size(0):
        raise ValueError('The input tables must have the same batch size')
    logits, pair_token = model(a, b, requests, mask=mask)
    make, finish = decode(logits)
    return make, finish, pair_token


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arm', choices=('learned', 'static', 'aux'), required=True)
    parser.add_argument('--checkpoint', type=Path, required=True, help='trained model.pt state_dict')
    parser.add_argument('--plan', type=Path, required=True, help='compiled plan.json used during training')
    parser.add_argument('--input', type=Path, help='JSON with a, b and requests; defaults to an identity collision')
    parser.add_argument('--mask', choices=('none', 'parents', 'parents_latent'), default='none')
    parser.add_argument('--device', choices=('auto', 'cpu', 'mps', 'cuda'), default='auto')
    args = parser.parse_args()
    device = select_device(args.device)
    fit_file = args.checkpoint.with_name('fit.json')
    if fit_file.is_file():
        fit = json.loads(fit_file.read_text())
        if fit['arm'] != args.arm or fit['plan_sha256'] != hashlib.sha256(args.plan.read_bytes()).hexdigest():
            raise ValueError('Arm or plan differs from the training checkpoint metadata')
        if fit['model_sha256'] != hashlib.sha256(args.checkpoint.read_bytes()).hexdigest():
            raise ValueError('Checkpoint weights differ from fit.json')
    model = CrossRun(args.arm, args.plan).to(device)
    model.load_state_dict(torch.load(args.checkpoint, map_location=device, weights_only=True), strict=True)
    model.eval()
    source = json.loads(args.input.read_text()) if args.input else DEMO
    make, finish, pair_token = predict(model, source, device, args.mask)
    result = {key: {name: tensor.cpu().tolist() for name, tensor in stage.items()}
              for key, stage in (('make', make), ('finish', finish))}
    result['pair_token'] = pair_token.cpu().tolist()
    result['device'] = str(device)
    print(json.dumps(result, allow_nan=False))


if __name__ == '__main__':
    main()
