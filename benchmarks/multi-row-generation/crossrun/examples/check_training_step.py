"""Compare offline label alignment, loss and per-parameter gradients on identical tensors."""
import argparse
import json
from pathlib import Path
import sys

import eggfuse
import mlx.core as mx
import mlx.nn as nn
from mlx.utils import tree_flatten
import numpy as np

from train import training_loss
from training_support import ASSETS, align_training_targets, load_asset, load_training_set


def gradient_snapshot(model, loss, inputs, targets):
    value, gradients = nn.value_and_grad(model, loss)(model, *inputs, *targets)
    mx.eval(value, gradients)
    return float(value), {key: np.asarray(value) for key, value in tree_flatten(gradients)}


def compare_gradients(first, second):
    assert first.keys() == second.keys()
    errors = {k: float(np.max(np.abs(first[k] - second[k]))) for k in first}
    max_error = max(errors.values())
    distance = np.sqrt(sum(np.sum((first[k].astype(float)-second[k])**2) for k in first))
    norm = np.sqrt(sum(np.sum(first[k].astype(float)**2) for k in first))
    return dict(tensors=len(first), tensors_with_difference=sum(v > 0 for v in errors.values()),
                max_abs=max_error, relative_l2=float(distance / max(norm, 1e-30)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    mx.set_default_device(mx.gpu)
    experiment = ASSETS / 'crossrun'
    sys.path.insert(0, str(experiment))
    import fit as reference_fit
    from cross_model import CrossRun, projection_recipe

    meta = json.loads((args.reference / 'fit.json').read_text())
    plan = experiment / 'compiler/plan.json'
    original = CrossRun(meta['arm'], projection_recipe(plan))
    packaged = eggfuse.CrossRun(meta['arm'], eggfuse.projection_recipe(plan))
    initial = args.reference / 'initial.safetensors'
    for model in (original, packaged):
        model.load_weights(str(initial))
        mx.eval(model.parameters())
    training = load_training_set(ASSETS, None)
    indices = np.random.default_rng(meta['seed']).integers(len(training['a']), size=32)
    inputs = [mx.array(training[key][indices]) for key in ('a', 'b', 'requests')]
    sources = [training[key][indices] for key in ('requests', 'target1', 'target2')]
    ref_stages, ref_token = original(*inputs)
    new_stages, new_token = packaged(*inputs)
    mx.eval(ref_stages, ref_token, new_stages, new_token)
    np.testing.assert_array_equal(np.asarray(ref_token), np.asarray(new_token))
    for left, right in zip(ref_stages, new_stages):
        for expected, actual in zip(left, right):
            np.testing.assert_array_equal(np.asarray(expected), np.asarray(actual))
    solve = load_asset(ASSETS / 'allocation/assignment.py').assign
    target_ref = reference_fit.training_labels(ref_stages[0][:3], ref_stages[1][:3], *sources)
    target_new = align_training_targets(new_stages[0][:3], new_stages[1][:3], *sources, solve)
    for expected, actual in zip(target_ref, target_new):
        np.testing.assert_array_equal(expected, actual)
    targets = [mx.array(x) for x in target_ref]
    ref_loss, ref_gradients = gradient_snapshot(original, reference_fit.loss, inputs, targets)
    new_loss, new_gradients = gradient_snapshot(packaged, training_loss, inputs, targets)
    repeated_loss, repeated_gradients = gradient_snapshot(original, reference_fit.loss, inputs, targets)
    report = dict(initial_logits_and_token_exact=True, pair_and_result_training_labels_exact=True,
                  interpreted_first_batch_losses=[ref_loss,new_loss,repeated_loss],
                  package_vs_reference=compare_gradients(ref_gradients, new_gradients),
                  original_vs_itself=compare_gradients(ref_gradients, repeated_gradients))
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    np.testing.assert_allclose(new_loss, ref_loss, rtol=1e-6)
    assert report['package_vs_reference']['relative_l2'] < 1e-5


if __name__ == '__main__':
    main()
