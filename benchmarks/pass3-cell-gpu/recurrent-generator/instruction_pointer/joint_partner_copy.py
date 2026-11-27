"""Canonical CCP ablation of the neural last-address copy pathway, with paired draws."""

import numpy as np
import torch
from first_parent import records
from joint_partner import model
from joint_partner_worlds import options, folder
from joint_partner_eval import generate
from binding_online import trial
from completion_context import native


def measure(a):
    rows = []
    for seed in a.seeds:
        nets = {arm: model(a, seed, arm) for arm in ("independent", "wide")}
        for n in (256, 512, 1024):
            for k in range(3):
                for flip in (0, 1):
                    i = 300001 + 8 * k
                    d = folder(a, ("held", i, n, "two", flip, True))
                    ref = native(a, d, "reference", "-")["state_sha"]
                    for block in (0, 1):
                        jobs = [(arm, copy) for arm in nets for copy in (True, False)]
                        for arm, copy in jobs if not block else reversed(jobs):
                            issue = generate(nets[arm])

                            def propose(client, z, program, rng):
                                if not copy:
                                    z = dict(
                                        z,
                                        banks=[
                                            dict(bank, last=-1) for bank in z["banks"]
                                        ],
                                    )
                                # New draw for each program and model seed, paired across arms.
                                draw = np.random.default_rng(
                                    np.random.SeedSequence((seed, n, k, flip))
                                )
                                return issue(client, z, program, draw)

                            row = trial(a, d, arm, nets[arm], seed, generate=propose)
                            assert (row["graph"] == ref) == bool(row["ops"])
                            row.pop("receipts")
                            rows.append(
                                dict(
                                    row,
                                    copy=int(copy),
                                    instance=i,
                                    flip=flip,
                                    block=block,
                                )
                            )
        records(a.out / "copy-online.csv", rows)
        print(seed, len(rows), flush=True)


if __name__ == "__main__":
    a = options().parse_args()
    torch.set_num_threads(1)
    measure(a)
