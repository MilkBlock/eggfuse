"""Exclusive native evaluation with the frozen transaction policy."""

import argparse
from pathlib import Path

import torch

from transaction_native import execute
from txn_policy import ResponsePolicy

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument(
        "mode", choices=("learned", "always", "random-address", "chain")
    )
    parser.add_argument("cases", nargs="+")
    parser.add_argument("--seconds", type=float, default=120)
    args = parser.parse_args()
    torch.set_num_threads(1)
    for case in args.cases:
        result = execute(
            args.root,
            case,
            seconds=args.seconds,
            study=ResponsePolicy(args.root, args.mode),
            series="txn-" + args.mode,
        )
        print(
            case,
            result["exact_endpoint"],
            result["paid"],
            result["eps"],
            result["termination"],
            flush=True,
        )
