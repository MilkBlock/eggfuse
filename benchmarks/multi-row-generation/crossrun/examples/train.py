"""Fit the two-Run EggFuse model on the frozen unordered binding dataset."""
import argparse
import hashlib
import json
from pathlib import Path
import time

import eggfuse
import mlx.core as mx
import mlx.nn as nn
import mlx.optimizers as optim
import numpy as np

from training_support import ASSETS, align_training_targets, load_asset, load_training_set, training_digest


def training_loss(model, a, b, requests, pair_targets, result_targets):
    # finish consumes the Pair token that make actually generated. Labels are
    # used below for losses only. In aux, field logits come from training heads.
    stages, _ = model(a, b, requests, training_heads=True)
    total = mx.array(0.0)
    for (active_logits, left_logits, right_logits, field_logits), targets in zip(stages, (pair_targets, result_targets)):
        active = targets[..., 0]
        total += nn.losses.cross_entropy(active_logits, active, reduction='mean')
        for column, scores in enumerate((left_logits, right_logits), start=1):
            total += mx.mean(active * nn.losses.cross_entropy(scores, targets[..., column]))
        if model.arm in ('learned', 'aux'):
            for column, (start, stop) in enumerate(((0, 8), (8, 12), (12, 16)), start=3):
                total += mx.mean(active * nn.losses.cross_entropy(field_logits[..., start:stop], targets[..., column]))
    return total


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fit(args):
    if not mx.metal.is_available():
        raise RuntimeError('The published experiment requires a Metal GPU')
    if args.steps < 1:
        raise ValueError('--steps must be positive')
    mx.set_default_device(mx.gpu)
    mx.random.seed(args.seed)
    rng = np.random.default_rng(args.seed)
    parent_weights = args.parent / 'model.safetensors'
    parent_info = json.loads((args.parent / 'result.json').read_text())
    if parent_info['model_sha256'] != sha256(parent_weights) or parent_info['protocol']['seed'] != args.seed:
        raise ValueError('Parent checkpoint hash or seed differs from the streaming experiment')

    model = eggfuse.CrossRun(args.arm, eggfuse.projection_recipe(args.plan))
    model.make.load_weights(str(parent_weights))
    mx.eval(model.parameters())
    training = load_training_set(args.assets, args.data)
    solve = load_asset(args.assets / 'allocation/assignment.py').assign

    args.output.mkdir(parents=True, exist_ok=False)
    initial_weights = args.output / 'initial.safetensors'
    model.save_weights(str(initial_weights))
    optimizer = optim.Adam(learning_rate=0.0003)
    gradients = nn.value_and_grad(model, training_loss)
    state = [model.state, optimizer.state]

    def predict_slots(a, b, requests):
        stages, _ = model(a, b, requests)
        return [stage[:3] for stage in stages]

    def update(a, b, requests, pairs, results):
        loss, grads = gradients(model, a, b, requests, pairs, results)
        optimizer.update(model, grads)
        return loss

    predict_slots = mx.compile(predict_slots, inputs=model.state)
    update = mx.compile(update, inputs=state, outputs=state)
    history = []
    start_time = time.perf_counter()
    for step in range(args.steps):
        index = rng.integers(len(training['a']), size=32)
        a, b, requests = (mx.array(training[name][index]) for name in ('a', 'b', 'requests'))
        make_scores, finish_scores = predict_slots(a, b, requests)
        mx.eval(make_scores, finish_scores)
        pairs, results = align_training_targets(
            make_scores, finish_scores, training['requests'][index],
            training['target1'][index], training['target2'][index], solve,
        )
        loss = update(a, b, requests, mx.array(pairs), mx.array(results))
        mx.eval(loss, state)
        if step % 500 == 0 or step + 1 == args.steps:
            entry = dict(step=step + 1, loss=float(loss), seconds=time.perf_counter() - start_time)
            if not np.isfinite(entry['loss']):
                raise ValueError(f'Nonfinite training loss at step {step + 1}')
            history.append(entry)
            print(json.dumps(entry), flush=True)

    final_weights = args.output / 'model.safetensors'
    model.save_weights(str(final_weights))
    metadata = dict(arm=args.arm, seed=args.seed, steps=args.steps, history=history,
                    parent_sha256=parent_info['model_sha256'], plan_sha256=sha256(args.plan),
                    initial_sha256=sha256(initial_weights), model_sha256=sha256(final_weights),
                    training_input_sha256=training_digest(training))
    (args.output / 'fit.json').write_text(json.dumps(metadata, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parent', type=Path, required=True, help='streaming feedback checkpoint directory')
    parser.add_argument('--output', type=Path, required=True, help='new checkpoint directory')
    parser.add_argument('--assets', type=Path, default=ASSETS, help='benchmarks/multi-row-generation directory')
    parser.add_argument('--plan', type=Path, help='compiler projection plan (default: <assets>/crossrun/compiler/plan.json)')
    parser.add_argument('--data', type=Path, help='optional NPZ with a, b, requests, target1, target2 arrays')
    parser.add_argument('--arm', choices=('learned', 'static', 'aux'), default='aux')
    parser.add_argument('--seed', type=int, choices=(1703, 1709), default=1703)
    parser.add_argument('--steps', type=int, default=2000)
    args = parser.parse_args()
    if args.plan is None:
        args.plan = args.assets / 'crossrun/compiler/plan.json'
    fit(args)


if __name__ == '__main__':
    main()
