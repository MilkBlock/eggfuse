"""Historical weights and cursor with the same per-Run paid upper bound and address permutation."""

from time import perf_counter

import torch

from completion_context import read, write
from discrete_reference import Reference
from partner_index_worlds import args
from recursive_coverage import Target
from recursive_train import folder
from transaction_native import execute


@torch.no_grad()
def run(a):
    rows = []
    for case in ("fact", "loopfact", "sum-divisors"):
        d = folder(a.data, case)
        target = Target(read(d / "program.json"), read(a.out / case / "ref.json"))
        initial = target.match(read(a.out / case / "init.json"))
        for block in range(2):
            t = perf_counter()
            policy = Reference(True, run_request_cap=8)
            setup = perf_counter() - t
            path = a.out / "stream" / case / str(block)
            result = execute(
                a.data,
                case,
                study=policy,
                series=str(path),
                seconds=400,
                address_seed=179636,
            )
            assert result["termination"] == "schedule_end"
            facts = sorted(
                target.match(read(path / (case + "-stream-multi") / "state.json"))
                - initial
            )
            wall = result["wall"] + result["runtime_setup_seconds"] + setup
            row = {
                "case": case,
                "block": block,
                "covered": len(facts),
                "reference": len(target.gold) - len(initial),
                "facts": facts,
                "paid": result["paid"],
                "ops": result["signed_ops"],
                "graph": result["state_sha"],
                "wall": wall,
                "eps": result["signed_ops"] / wall,
                "ept": result["signed_ops"] / max(1, result["paid"]),
            }
            rows.append(row)
            write(a.out / "stream.json", rows)
            print(case, block, row["covered"], row["paid"], flush=True)


if __name__ == "__main__":
    torch.set_num_threads(1)
    run(args())
