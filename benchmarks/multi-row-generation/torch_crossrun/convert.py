"""Convert a verified MLX safetensors checkpoint to an ordinary PyTorch state_dict."""
import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path

import torch
from safetensors.torch import load_file

from model import CrossRun


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def convert_checkpoint(source, expected_hash, destination, model):
    if sha256(source) != expected_hash:
        raise ValueError(f"Source hash differs from fit.json: {source}")
    weights = load_file(str(source), device="cpu")
    required = model.state_dict()
    if weights.keys() != required.keys():
        raise ValueError(f"Parameter keys differ: {set(weights) ^ set(required)}")
    for name, tensor in weights.items():
        other = required[name]
        if tensor.shape != other.shape or tensor.dtype != other.dtype:
            raise ValueError(f"{source}: incompatible parameter {name}")
    model.load_state_dict(weights, strict=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        previous = torch.load(destination, weights_only=True, map_location="cpu")
        if previous.keys() != weights.keys() or any(
                t.shape != previous[k].shape or t.dtype != previous[k].dtype
                or not torch.equal(t.reshape(-1).view(torch.uint8), previous[k].reshape(-1).view(torch.uint8))
                for k, t in weights.items()):
            raise FileExistsError(f"Existing checkpoint differs: {destination}")
        return dict(source_sha256=expected_hash, converted_sha256=sha256(destination),
                    tensors=len(weights), parameter_bytes=sum(x.nbytes for x in weights.values()))
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as handle:
        temp = Path(handle.name)
    try:
        with temp.open("wb") as stream:
            torch.save(model.state_dict(), stream)
        restored = torch.load(temp, weights_only=True, map_location="cpu")
        for name, tensor in weights.items():
            assert torch.equal(tensor.reshape(-1).view(torch.uint8),
                               restored[name].reshape(-1).view(torch.uint8)), name
        os.replace(temp, destination)
    finally:
        temp.unlink(missing_ok=True)
    return dict(source_sha256=expected_hash, converted_sha256=sha256(destination),
                tensors=len(weights), parameter_bytes=sum(x.nbytes for x in weights.values()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mlx-root", required=True, type=Path)
    parser.add_argument("--torch-root", required=True, type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    args = parser.parse_args()
    report = {}
    for arm in ("learned", "static", "aux"):
        for seed in (1703, 1709):
            name = f"{arm}-{seed}"
            source_dir = args.mlx_root / name
            info = json.loads((source_dir / "fit.json").read_text())
            assert (info["arm"], info["seed"], info["plan_sha256"]) == (arm, seed, sha256(args.plan))
            model = CrossRun(arm, args.plan)
            report[name] = {}
            for src, dst, key in (("model.safetensors", "final.pt", "model_sha256"),
                                  ("initial.safetensors", "initial.pt", "initial_sha256")):
                report[name][dst] = convert_checkpoint(source_dir / src, info[key],
                                                       args.torch_root / name / dst, model)
    (args.torch_root / "conversion.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Converted {len(report)} final checkpoints and their initialization tensors.")


if __name__ == "__main__":
    main()
