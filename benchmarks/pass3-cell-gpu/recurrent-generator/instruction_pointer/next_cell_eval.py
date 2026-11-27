"""Matched slot and completed-token budgets, on disjoint teacher and model states."""

from pathlib import Path
import torch
from discovery_states import cli
from throughput_frozen import frozen

if __name__ == "__main__":
    p = cli()
    p.add_argument("--archive", required=True, type=Path)
    p.add_argument(
        "--arms",
        nargs="+",
        default=["factored", "initial", "ce24", "ce200", "ce200mixed"],
    )
    p.add_argument("--seeds", nargs="+", type=int, default=[9633, 5003])
    p.add_argument("--states", type=int, default=4)
    a = p.parse_args()
    torch.set_num_threads(1)
    for seed in a.seeds:
        for case in a.cases:
            for source in ("teacher", "rollout"):
                frozen(
                    a,
                    case,
                    source,
                    fit_seed=seed,
                    states=a.states,
                    destination=f"paired-{seed}",
                    native_trial=lambda arm, kind, budget: (
                        (kind, budget) in (("slots", 256), ("complete", 16))
                    ),
                )
