"""Paired native rollout ablations. All weight updates use the existing B ES return."""

import argparse
from pathlib import Path
from time import perf_counter

import torch

from protocol_experiment import dump
from recursive_ripsat import OpenEntries
from recursive_ripsat_study import episode, setup_policy, train
from structure_runtime import PointerEntries, StructureEntries

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("data", type=Path)
    p.add_argument("store", type=Path)
    p.add_argument("case")
    p.add_argument("arms", nargs="+", choices=["train", "recent", "pointer", "structure", "rl"])
    p.add_argument("--setup-only", action="store_true")
    p.add_argument("--rep", type=int, default=0)
    p.add_argument("--limit", type=int)
    p.add_argument("--steps", type=int, default=4)
    p.add_argument("--seed", type=int, default=431)
    p.add_argument("--sigma", type=float, default=0.06)
    a = p.parse_args()
    torch.set_num_threads(1)
    for arm in a.arms:
        if arm == "train":
            train(a, StructureEntries, "recursive-rl.pt", "structure-rl.pt")
        else:
            cls = {
                "recent": OpenEntries,
                "pointer": PointerEntries,
                "structure": StructureEntries,
                "rl": StructureEntries,
            }[arm]
            weights = "structure-rl.pt" if arm == "rl" else "recursive-rl.pt"
            if a.setup_only:
                start = perf_counter()
                state = torch.load(a.store / weights, weights_only=True)
                setup_policy(a.data, a.store, a.case, state, True, policy_cls=cls)
                dump(a.store / f"{a.case}-{arm}-setup-{a.rep}.json", {"seconds": perf_counter() - start})
                continue
            episode(
                a.data,
                a.store,
                a.case,
                f"{arm}-{a.rep}",
                torch.load(a.store / weights, weights_only=True),
                True,
                a.limit,
                policy_cls=cls,
            )
