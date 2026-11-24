"""Check the Recipe-based request frontier on real programs and bound-role prefixes."""

from argparse import ArgumentParser
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
import json
import subprocess

from composition_relation import Interfaces
from receipt_bake import read, save
from txn_policy import plans, request_frontier


def check(program_path, binary):
    p = read(program_path)
    native = json.loads(
        subprocess.check_output([binary, "receipt-contract", program_path])
    )
    before = Interfaces({k: v for k, v in p.items() if k != "receipt_contract"})
    after = Interfaces(dict(p, receipt_contract=native))
    if before.exports != after.exports:
        raise ValueError("named table inventory differs")
    counts = Counter()
    for rid, rule in enumerate(native["rules"]):
        roles = range(len(rule["inputs"]))
        for target in roles:
            remaining = tuple(r for r in roles if r != target)
            # Test source order, reverse order, and each single bound neighbor.
            prefixes = {(), remaining, remaining[::-1], *((r,) for r in remaining)}
            for prefix in prefixes:
                order = (*prefix, target)
                for chain in (False, True):
                    saved = plans(
                        SimpleNamespace(iface=before),
                        rid,
                        len(prefix),
                        chain,
                        order=order,
                    )
                    actual = plans(
                        SimpleNamespace(iface=after),
                        rid,
                        len(prefix),
                        chain,
                        order=order,
                    )
                    if not set(saved) <= set(actual):
                        raise ValueError((rid, order, saved, actual))
                    states = tuple(
                        "available" if i in prefix else "unbound" for i in roles
                    )
                    if tuple(sorted(prefix)) == prefix:
                        frontier = request_frontier(rule, states, chains=chain)
                        if actual != frontier["computations"][target]:
                            raise ValueError(
                                "frontier inconsistent with transaction planner"
                            )
                    counts["inspected"] += 1
                    counts["previous_plans"] += len(saved)
                    counts["compiled_plans"] += len(actual)
                    counts["plans_with_local_inputs"] += sum(
                        bool(p.prerequisites) for p in actual
                    )
    return counts


if __name__ == "__main__":
    p = ArgumentParser()
    p.add_argument("binary", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("programs", type=Path, nargs="+")
    args = p.parse_args()
    save(args.output, {f.parent.name: check(f, args.binary) for f in args.programs})
