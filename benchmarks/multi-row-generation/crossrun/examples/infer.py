"""Read raw source tables, run make and finish on Metal, and print decoded proposals."""
import argparse
import json
from pathlib import Path

import eggfuse
import mlx.core as mx


DEMO = dict(
    a=[[3, 1], [3, 1], [5, 2], [7, 0]],
    b=[[3, 2], [4, 0], [5, 0], [6, 1]],
    requests=[[1, 0, 2], [2, 2, 1], [3, 1, 0], [0, 3, 3]],
)


def predict(model, source, mask):
    stages, pair_token = eggfuse.infer(model, source['a'], source['b'], source['requests'], mask=mask)
    mx.eval(stages, pair_token)
    # Read GPU outputs after finish has consumed the actual make token.
    make, finish = ({field: values.tolist() for field, values in stage.items()} for stage in stages)
    return dict(make=make, finish=finish, pair_token=pair_token.tolist())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', type=Path, required=True, help='directory with model.safetensors and fit.json')
    parser.add_argument('--plan', type=Path, required=True, help='the compiled plan used for this checkpoint')
    parser.add_argument('--input', type=Path, help='JSON with a, b and requests; defaults to a parent-collision example')
    parser.add_argument('--mask', choices=('none', 'parents', 'parents_latent'), default='none')
    args = parser.parse_args()

    source = json.loads(args.input.read_text()) if args.input else DEMO
    model = eggfuse.load_model(args.checkpoint, args.plan)
    print(json.dumps(predict(model, source, args.mask), allow_nan=False))


if __name__ == '__main__':
    main()
