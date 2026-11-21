"""Offline PyTorch fit on generated local contexts; write a frozen CPU-readable head."""
import argparse
import json
import os
from pathlib import Path
from runpy import run_path

import torch
from fragments import digest, occurrences
from policy import training_set

HERE = Path(__file__).resolve().parent


def fit(paths, device):
    programs = {}
    for path in paths:
        for program, _ in occurrences(json.loads(path.read_bytes())):
            programs[digest(program)] = program
    xs, ys = training_set([programs[k] for k in sorted(programs)])
    x = torch.from_numpy(xs).to(device)
    y = torch.from_numpy(ys).to(device)
    # Conjugate gradient on the positive definite ridge system. All matrix
    # products, gradients and weight updates stay on the selected device.
    gram = x.T @ x + torch.eye(x.shape[1], device=device)
    rhs = x.T @ y
    # Diagonal preconditioning keeps the small f32 solve accurate on MPS.
    scale = gram.diag().rsqrt()
    a = scale[:, None] * gram * scale[None, :]
    b = scale * rhs
    w = torch.zeros_like(b)
    residual = b.clone()
    direction = residual.clone()
    for _ in range(32):
        old = residual @ residual
        product = a @ direction
        alpha = old / (direction @ product).clamp_min(1e-30)
        w = w + alpha * direction
        updated = residual - alpha * product
        direction = updated + ((updated @ updated) / old.clamp_min(1e-30)) * direction
        residual = updated
    weights = scale * w
    error = ((gram @ weights - rhs).norm() / rhs.norm()).item()
    if not error < 1e-5:
        raise ValueError(f"ridge normal-equation residual {error}")
    return dict(schema="eggfuse-fragment-ridge/v1", weights=weights.cpu().tolist(),
                features=["bias","ops","ports","arguments","tables","shared_returns","scalar_ports"],
                training_shapes=len(programs), seed=1703, training_device=str(weights.device),
                torch_version=str(torch.__version__), relative_residual=error)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--donor", action="append", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--device", choices=["mps","cpu"], default="mps")
    args = parser.parse_args()
    if args.device == "mps" and os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK") != "0":
        parser.error("MPS training requires PYTORCH_ENABLE_MPS_FALLBACK=0")
    checkpoint = fit(args.donor,args.device)
    write = run_path(str(HERE.parent/"explicit-parent-cell-composition/ripsat_bridge.py"))["write_artifact"]
    write(args.out,checkpoint)
    print(checkpoint)
