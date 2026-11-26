"""Identical native generator and budget for all trained policies and the random baseline."""

import shutil
from pathlib import Path

import torch

from coverage_eval import frozen, independent
from discovery_states import cli

FIXED = [
    f"{a}-n152-u192"
    for a in (
        "teacher",
        "self",
        "omission",
        "duplicate",
        "failure",
        "shuffle",
        "downstream",
        "mixed",
    )
]
CURVE = [
    "omission-n16-u192",
    "omission-n64-u192",
    *[f"omission-n{n}-u1216" for n in (16, 64, 152)],
]
FINAL = ["mixed-n480-u192", "mixed-n480-u1920"]


if __name__ == "__main__":
    p = cli()
    p.add_argument("mode", choices=["native", "frozen"])
    p.add_argument("--archive", required=True, type=Path)
    p.add_argument("--initial", required=True, type=Path)
    p.add_argument("--seeds", type=int, nargs="+", default=[9633, 5003])
    p.add_argument("--arms", nargs="+", default=["initial", *FIXED, *CURVE, *FINAL])
    a = p.parse_args()
    torch.set_num_threads(1)
    for seed in a.seeds:
        shutil.copyfile(a.initial, a.out / "weights" / str(seed) / "initial.pt")
    if a.mode == "native":
        independent(a, a.arms)
    else:
        for case in a.cases:
            frozen(a, case, "rollout", a.arms, draws=2)
