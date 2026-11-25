"""Profile, train, and independently run the same recursive B policy."""

import argparse
from pathlib import Path

import torch

from cost_profile import ProfileEntries
from recursive_ripsat_study import episode, train
from structure_runtime import StructureEntries

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("data", type=Path)
    p.add_argument("store", type=Path)
    p.add_argument("case")
    p.add_argument("arms", nargs="+")
    p.add_argument("--limit", type=int)
    p.add_argument("--rep", type=int, default=0)
    p.add_argument("--steps", type=int, default=4)
    p.add_argument("--sigma", type=float, default=0.06)
    p.add_argument("--seed", type=int, default=431)
    a = p.parse_args()
    torch.set_num_threads(1)
    for arm in a.arms:
        if arm in ("profile", "base"):
            cls = ProfileEntries if arm == "profile" else StructureEntries
        elif arm == "aux":
            from cost_aux import AuxiliaryProfile

            cls = AuxiliaryProfile
        elif arm in ("receipt", "receipt-single", "combined", "receipt-with-b"):
            from cost_receipts import (
                CombinedOracle,
                ReceiptOracle,
                ReceiptWithFrozenB,
                SingleReceiptOracle,
            )

            cls = {
                "receipt": ReceiptOracle,
                "receipt-single": SingleReceiptOracle,
                "combined": CombinedOracle,
                "receipt-with-b": ReceiptWithFrozenB,
            }[arm]
        else:
            from cost_bake import (
                LearnedCostEntries,
                OracleCostEntries,
                SingleCostEntries,
                WideCostOracle,
            )

            cls = {
                "train": LearnedCostEntries,
                "frozen": LearnedCostEntries,
                "rl": LearnedCostEntries,
                "oracle": OracleCostEntries,
                "wide": WideCostOracle,
                "single": SingleCostEntries,
            }[arm]
        if arm == "train":
            if a.case != "sum":
                raise ValueError("Only the donor sum-bits may update these weights")
            train(a, cls, "structure-rl.pt", "cost-rl.pt")
        else:
            weights = torch.load(
                a.store / ("cost-rl.pt" if arm == "rl" else "structure-rl.pt"), weights_only=True
            )
            episode(
                a.data,
                a.store,
                a.case,
                f"{arm}-{a.rep}",
                weights,
                True,
                a.limit,
                policy_cls=cls,
                boundary_audit=True,
                keep_tape=a.store / f"{a.case}-{arm}-issued.json"
                if arm in ("receipt-with-b", "aux")
                else None,
            )
