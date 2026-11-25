"""Continue the unchanged B RL objective with publication-time region actions."""

import argparse
from pathlib import Path

import torch

from evidence_execution import EvidenceEntries
from recursive_ripsat_study import episode, train
from structure_runtime import StructureEntries

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("data", type=Path)
    p.add_argument("store", type=Path)
    p.add_argument("case")
    p.add_argument("arms", nargs="+", choices=["train", "late", "early", "rl"])
    p.add_argument("--seed", type=int, default=431)
    p.add_argument("--steps", type=int, default=4)
    p.add_argument("--sigma", type=float, default=0.06)
    p.add_argument("--limit", type=int)
    p.add_argument("--rep", type=int, default=0)
    a = p.parse_args()
    torch.set_num_threads(1)
    for arm in a.arms:
        if arm == "train":
            train(a, EvidenceEntries, "structure-rl.pt", "evidence-rl.pt")
        else:
            state = torch.load(
                a.store / ("evidence-rl.pt" if arm == "rl" else "structure-rl.pt"), weights_only=True
            )
            episode(
                a.data,
                a.store,
                a.case,
                f"{arm}-{a.rep}",
                state,
                True,
                a.limit,
                policy_cls=StructureEntries if arm == "late" else EvidenceEntries,
            )
