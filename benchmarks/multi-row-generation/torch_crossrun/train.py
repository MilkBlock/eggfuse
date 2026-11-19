"""Train a two-Run PyTorch model on the frozen Cell instance-binding task."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
import torch
import torch.nn.functional as F

from infer import select_device
from model import CrossRun

# These helpers implement the original NumPy-only dataset and training-time
# Hungarian label alignment. The online inference module has no such imports.
ASSETS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ASSETS / 'crossrun/examples'))
from training_support import align_training_targets, load_asset, load_training_set, training_digest


def categorical_loss(scores, target):
    return F.cross_entropy(scores.flatten(0, 1), target.flatten(), reduction='none').reshape_as(target)


def training_loss(stages, targets, arm):
    total = stages[0][0].new_zeros(())
    for (active, left, right, fields), target in zip(stages, targets):
        live = target[..., 0]
        total = total + categorical_loss(active, live).mean()
        for column, scores in enumerate((left, right), start=1):
            total = total + (live * categorical_loss(scores, target[..., column])).mean()
        if arm != 'static':
            for column, (start, stop) in enumerate(((0, 8), (8, 12), (12, 16)), start=3):
                total = total + (live * categorical_loss(fields[..., start:stop], target[..., column])).mean()
    return total


class ExperimentAdam:
    """The reference fit uses Adam with uncorrected moments and zero weight decay."""

    def __init__(self, parameters, lr=0.0003):
        self.lr = lr
        self.parameters = list(parameters)
        self.first = [torch.zeros_like(p) for p in self.parameters]
        self.second = [torch.zeros_like(p) for p in self.parameters]

    @torch.no_grad()
    def step(self):
        for parameter, first, second in zip(self.parameters, self.first, self.second):
            grad = parameter.grad
            if grad is not None:
                first.mul_(0.9).add_(grad, alpha=0.1)
                second.mul_(0.999).addcmul_(grad, grad, value=0.001)
                parameter.addcdiv_(first, second.sqrt().add_(1e-8), value=-self.lr)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fit(args):
    if args.steps < 1:
        raise ValueError('--steps must be positive')
    if args.output.exists():
        raise FileExistsError(f'Please choose a new output directory: {args.output}')
    device = select_device(args.device)
    rng = np.random.default_rng(args.seed)
    torch.manual_seed(args.seed)
    model = CrossRun(args.arm, args.plan).to(device)
    model.load_state_dict(torch.load(args.init, map_location=device, weights_only=True), strict=True)
    model.train()
    training = load_training_set(ASSETS, args.data)
    solve = load_asset(ASSETS / 'allocation/assignment.py').assign
    optimizer = ExperimentAdam(model.parameters())
    args.output.mkdir(parents=True, exist_ok=False)
    start_time = time.perf_counter()
    history = []
    for step in range(args.steps):
        batch = rng.integers(len(training['a']), size=32)
        a, b, requests = (torch.as_tensor(training[key][batch], device=device, dtype=torch.long)
                          for key in ('a', 'b', 'requests'))
        model.zero_grad(set_to_none=True)
        # The second Run reads the Pair tokens generated in this forward. Labels
        # are aligned afterwards. Only activation and pointer scores affect the assignment.
        stages, _ = model(a, b, requests, training_heads=True)
        scores = [[tensor.detach().cpu().numpy() for tensor in stage[:3]] for stage in stages]
        targets = align_training_targets(scores[0], scores[1], training['requests'][batch],
                                        training['target1'][batch], training['target2'][batch], solve)
        targets = [torch.as_tensor(target, device=device, dtype=torch.long) for target in targets]
        loss = training_loss(stages, targets, args.arm)
        loss.backward()
        optimizer.step()
        if step % 500 == 0 or step + 1 == args.steps:
            entry = dict(step=step + 1, loss=loss.item(), seconds=time.perf_counter() - start_time)
            if not np.isfinite(entry['loss']):
                raise ValueError(f'Nonfinite training loss at step {step + 1}')
            history.append(entry)
            print(json.dumps(entry), flush=True)

    checkpoint = args.output / 'model.pt'
    torch.save(model.state_dict(), checkpoint)
    metadata = dict(arm=args.arm, seed=args.seed, steps=args.steps, batch=32, device=str(device),
                    torch_version=str(torch.__version__), history=history, learning_rate=0.0003,
                    optimizer='Adam', betas=[0.9, 0.999], eps=1e-8, bias_correction=False,
                    initial_sha256=sha256(args.init), model_sha256=sha256(checkpoint),
                    plan_sha256=sha256(args.plan), training_input_sha256=training_digest(training))
    (args.output / 'fit.json').write_text(json.dumps(metadata, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arm', choices=('learned', 'static', 'aux'), required=True)
    parser.add_argument('--seed', type=int, choices=(1703, 1709), required=True)
    parser.add_argument('--init', type=Path, required=True, help='paired initialization as a torch state_dict')
    parser.add_argument('--plan', type=Path, required=True, help='compiled plan.json')
    parser.add_argument('--output', type=Path, required=True, help='new directory for model.pt and fit.json')
    parser.add_argument('--steps', type=int, default=2000)
    parser.add_argument('--device', choices=('auto', 'cpu', 'mps', 'cuda'), default='auto')
    parser.add_argument('--data', type=Path, help='optional frozen .npz with a, b, requests, target1, target2')
    fit(parser.parse_args())


if __name__ == '__main__':
    main()
