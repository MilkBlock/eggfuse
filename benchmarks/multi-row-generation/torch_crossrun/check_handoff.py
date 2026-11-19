"""Inspect the actual make/finish boundary of a converted PyTorch checkpoint."""
import argparse
import json
from pathlib import Path
import sys

import torch

from infer import DEMO, select_device
from model import CrossRun


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True, type=Path)
    parser.add_argument('--weights', required=True, type=Path)
    args = parser.parse_args()
    device = select_device("mps")
    model = CrossRun("aux", args.plan).to(device)
    model.load_state_dict(torch.load(args.weights, map_location=device, weights_only=True))
    trace = {}
    def produced(module, arguments, output):
        trace["produced"] = output[-1]
    def consumed(module, arguments):
        trace["consumed"] = arguments[0]
    first_hook = model.make.register_forward_hook(produced)
    second_hook = model.finish.register_forward_pre_hook(consumed)
    try:
        tables = [torch.tensor(DEMO[key], device=device).unsqueeze(0) for key in ("a","b","requests")]
        stages, pair = model(*tables)
        assert trace["produced"] is trace["consumed"] is pair
        assert pair.device.type == "mps" and tuple(pair.shape) == (1,8,90)
        grad, = torch.autograd.grad(stages[1][0].sum(), pair)
        assert grad[..., :64].abs().sum().item() > 0
        assert "eggfuse" not in sys.modules and "mlx.core" not in sys.modules
    finally:
        first_hook.remove()
        second_hook.remove()
    print(json.dumps(dict(same_tensor=True,device=str(pair.device),shape=list(pair.shape),
                          finish_to_make_gradient=True,loaded_eggfuse=False,loaded_mlx=False)))


if __name__ == "__main__":
    main()
