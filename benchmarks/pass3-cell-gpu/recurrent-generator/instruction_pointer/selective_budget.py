"""Paired budget frontier with fresh native address permutations and a fixed exit."""

from selective_worlds import args, path
from selective_kernel import net
from selective_trials import issue
from completion_context import native
from binding_online import trial
from first_parent import records
import torch


@torch.no_grad()
def run(a):
    rows = []
    for seed in a.seeds:
        models = {
            arm: net(a, seed, arm) for arm in ("wide", "joint-sparse", "mixed-sparse")
        }
        for domain in ("square", "near"):
            for n in (1024, 8192):
                for flip in (0, 1):
                    i = 300001
                    d = path(a, (domain, n, "two", i, flip))
                    ref = native(a, d, "reference", "-")["state_sha"]
                    jobs = [(arm, b) for arm in models for b in (1, 4, 32)]
                    for block in (0, 1):
                        for arm, b in jobs if not block else reversed(jobs):
                            addr = 33007 + i * 32771 + seed + flip
                            row = trial(
                                a,
                                d,
                                arm,
                                models[arm],
                                seed,
                                address_seed=addr,
                                generate=issue(
                                    models[arm], False, b, [seed, n, i, flip, 91]
                                ),
                            )
                            assert row["paid"] == b and bool(row["ops"]) == (
                                row["graph"] == ref
                            )
                            row.pop("receipts")
                            rows.append(
                                dict(
                                    row,
                                    domain=domain,
                                    n=n,
                                    budget=b,
                                    flip=flip,
                                    block=block,
                                    address_seed=addr,
                                )
                            )
                records(a.out / "budget.csv", rows)
        print(seed, len(rows), flush=True)


if __name__ == "__main__":
    torch.set_num_threads(1)
    run(args())
