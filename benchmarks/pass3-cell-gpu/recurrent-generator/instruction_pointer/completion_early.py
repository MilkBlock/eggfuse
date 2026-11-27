"""Replay the earliest available native and autonomous EggCC checkpoints."""

from pathlib import Path
import torch
from discovery_states import cli
from throughput_frozen import frozen


if __name__ == "__main__":
    p = cli()
    p.add_argument("--archive", type=Path, required=True)
    p.add_argument("--seeds", nargs="+", type=int, default=[9633, 5003, 1777])
    a = p.parse_args()
    a.arms = ["factored", "initial", "A", "B", "C"]
    torch.set_num_threads(1)
    for seed in a.seeds:
        for case in a.cases:
            for source in ["teacher", "rollout"]:
                frozen(
                    a,
                    case,
                    source,
                    states=3,
                    first_runs=True,
                    fit_seed=seed,
                    destination=f"early-{seed}",
                    native_trial=lambda arm, kind, b: kind == "slots" and b == 256,
                )
