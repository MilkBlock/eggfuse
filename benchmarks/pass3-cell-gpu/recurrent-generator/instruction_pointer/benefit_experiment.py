"""Independent, counterbalanced comparison; no online teacher or residual search."""

import argparse
from pathlib import Path
import torch
from benefit_policy import BenefitNet, BenefitPolicy
from protocol_experiment import digest, dump, run
from recursive_train import read
from txn_policy import ResponsePolicy

CASES = (
    "grammar-25112473",
    "grammar-stride3-split-7300147",
    "grammar-benefit-held-11901371",
    "grammar-benefit-held-deep-11901379",
    "cyk801",
    "fact",
    "sum-divisors",
)
ORDERS = (
    ("A", "fixed", "full", "residual"),
    ("fixed", "residual", "A", "full"),
    ("residual", "full", "fixed", "A"),
    ("full", "A", "residual", "fixed"),
)


def record_tapes(root, out, cases):
    for case in cases:
        path = out / (case + ".json")
        info = read(path)
        info["accepted_tape_sha256"] = {
            arm: digest(
                root
                / "computation-benefit"
                / case
                / arm
                / (case + "-stream-multi")
                / "issued.json"
            )
            for arm in ORDERS[0]
        }
        dump(path, info)


def compare(root, out, cases):
    weights = {arm: out / (arm + ".pt") for arm in ("full", "residual")}

    def policy(arm, route):
        if arm in ("A", "fixed"):
            study = ResponsePolicy(root, route)
            if arm == "fixed":
                study.chains = True
                study.mode = "always"
            return study
        net = BenefitNet().eval()
        net.load_state_dict(torch.load(weights[arm], weights_only=True))
        return BenefitPolicy(root, net, arm, route, activate=True)

    run(
        root,
        out,
        cases,
        policy_factory=policy,
        orders=ORDERS,
        series_prefix="computation-benefit",
        extra_weights=weights,
    )
    record_tapes(root, out, cases)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("cases", nargs="*")
    a = p.parse_args()
    compare(a.root, a.out, a.cases or CASES)
