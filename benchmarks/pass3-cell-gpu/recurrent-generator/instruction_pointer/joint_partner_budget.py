"""Paid-slot frontier on independent marginal-twin programs."""

import torch
from binding_online import trial
from first_parent import records
from completion_context import native
from joint_partner_eval import generate
from joint_partner import model
from joint_partner_worlds import options, folder


def budget(a):
    rows = []
    for seed in a.seeds:
        nets = {arm: model(a, seed, arm) for arm in ("independent", "tensor", "wide")}
        for n in (4, 32, 256, 512, 1024):
            for i in range(2):
                for flip in (0, 1):
                    d = folder(a, ("held", 300001 + 8 * i, n, "two", flip, True))
                    ref = native(a, d, "reference", "-")["state_sha"]
                    for block in (0, 1):
                        tasks = [(k, s) for s in (1, 4, 16, 32) for k in nets]
                        for arm, slots in tasks if block == 0 else reversed(tasks):
                            r = trial(
                                a,
                                d,
                                arm,
                                nets[arm],
                                seed,
                                generate=generate(nets[arm], slots),
                            )
                            assert r["paid"] == slots and (r["graph"] == ref) == bool(
                                r["ops"]
                            )
                            r.pop("receipts")
                            rows.append(
                                dict(
                                    r,
                                    block=block,
                                    instance=i,
                                    flip=flip,
                                    coverage=r["ops"],
                                )
                            )
        records(a.out / "budget.csv", rows)
        print(seed, len(rows), flush=True)


if __name__ == "__main__":
    a = options().parse_args()
    torch.set_num_threads(1)
    budget(a)
