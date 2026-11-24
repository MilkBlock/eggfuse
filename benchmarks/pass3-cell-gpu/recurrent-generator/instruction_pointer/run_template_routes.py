"""Counterbalance each transport separately, using a single frozen directory."""

import argparse
from pathlib import Path
import torch
from generation_higher import run as fused
from higher_replacement import run as ccp
from recursive_train import binary

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--cases", nargs="+", required=True)
    p.add_argument("--reps", type=int, default=4)
    p.add_argument("--modes", nargs="+", default=["atomic", "full", "direct", "sparse"])
    p.add_argument("--transport", choices=["ccp", "fused"], required=True)
    p.add_argument("--fraction", type=float, default=1)
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--learned-prefix", action="store_true")
    a = p.parse_args()
    torch.set_num_threads(1)
    for c in a.cases:
        for i in range(a.offset, a.offset + a.reps):
            for mode in a.modes if i % 2 == 0 else a.modes[::-1]:
                arm = "A" if mode == "atomic" else "D"
                if a.transport == "ccp":
                    ccp(
                        a.root,
                        a.out,
                        c,
                        arm,
                        i,
                        learned_prefix=a.learned_prefix,
                        route=mode,
                        fraction=a.fraction,
                    )
                else:
                    if a.learned_prefix:
                        raise ValueError(
                            "learned prefix supported on CCP in this comparison"
                        )
                    fused(a.root, a.out, c, arm, i, binary(a.root), mode, a.fraction)
