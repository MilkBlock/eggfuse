"""Check the example's training and inference against the original experiment."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import eggfuse
import mlx.core as mx
import numpy as np

from infer import DEMO


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--reproduction', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    example_dir = Path(__file__).resolve().parent
    experiment = example_dir.parent
    # Only the auditor imports the original research module. The CLI runs in a
    # new process using the installed wheel and explicit checkpoint/plan paths.
    sys.path.insert(0, str(experiment))
    import cross_model
    mx.set_default_device(mx.gpu)
    plan = experiment / 'compiler/plan.json'

    ref = json.loads((args.reference / 'fit.json').read_text())
    new = json.loads((args.reproduction / 'fit.json').read_text())
    for label in ('arm', 'seed', 'steps', 'training_input_sha256', 'parent_sha256', 'plan_sha256', 'initial_sha256'):
        if ref[label] != new[label]:
            raise AssertionError(f'{label} differs')
    weight_name = 'model.safetensors'
    for directory, meta in ((args.reference, ref), (args.reproduction, new)):
        if file_hash(directory / weight_name) != meta['model_sha256']:
            raise AssertionError(f'Weight file hash differs from {directory}/fit.json')
    recorded_losses = [[e['step'], e['loss']] for e in ref['history']]
    observed_losses = [[e['step'], e['loss']] for e in new['history']]
    train_exact = recorded_losses == observed_losses and ref['model_sha256'] == new['model_sha256']

    original = cross_model.CrossRun(new['arm'], cross_model.projection_recipe(plan))
    original.load_weights(str(args.reproduction / weight_name))
    original.eval()
    inputs = [mx.array(DEMO[k], dtype=mx.int32)[None] for k in ('a', 'b', 'requests')]
    checks = []
    for mask in ('none', 'parents', 'parents_latent'):
        command = [sys.executable, str(example_dir / 'infer.py'), '--checkpoint', str(args.reproduction),
                   '--plan', str(plan), '--mask', mask]
        output = json.loads(subprocess.check_output(command))
        stages, token = original(*inputs, mask=mask)
        decoded = cross_model.decode(stages)
        mx.eval(decoded, token)
        np.testing.assert_array_equal(np.asarray(token), np.asarray(output['pair_token'], dtype=np.float32))
        for stage, label in zip(decoded, ('make', 'finish')):
            for field, values in stage.items():
                np.testing.assert_array_equal(np.asarray(values), output[label][field])
        checks.append(mask)
    result = dict(arm=new['arm'], seed=new['seed'], steps=new['steps'],
                  working_directory=str(Path.cwd()), installed_package=str(Path(eggfuse.__file__).resolve()),
                  reference_model_sha256=ref['model_sha256'], example_model_sha256=new['model_sha256'],
                  training_input_sha256=new['training_input_sha256'], reference_losses=recorded_losses,
                  example_losses=observed_losses, training_bit_exact=train_exact,
                  cli_decode_and_pair_token_exact=checks)
    args.report.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)
    if not train_exact:
        raise SystemExit('Final weights or logged losses differ from the original training run.')


if __name__ == '__main__':
    main()
