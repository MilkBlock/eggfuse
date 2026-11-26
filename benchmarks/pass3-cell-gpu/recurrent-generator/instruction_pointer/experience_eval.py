"""Native evaluation. An identical pair of supervised arms uses one shared checkpoint."""

from pathlib import Path

import torch

from coverage_eval import frozen, independent
from coverage_fit import SEEDS
from discovery_states import cli, read

if __name__ == "__main__":
    p = cli()
    p.add_argument("mode", choices=["native", "frozen"])
    p.add_argument("--archive", required=True, type=Path)
    p.add_argument("--seeds", type=int, nargs="+", default=SEEDS)
    p.add_argument("--draws", type=int, default=2)
    a = p.parse_args()
    torch.set_num_threads(1)
    arms = [
        s for s in ("T", "TO", "TS", "TSO") if s not in read(a.out / "aliases.json")
    ]
    if a.mode == "native":
        independent(a, arms)
    else:
        for case in a.cases:
            for src in ("rollout", "teacher"):
                frozen(a, case, src, arms, a.draws)
