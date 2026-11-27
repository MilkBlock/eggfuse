"""Finite-particle reuse of the exact nonlinear head readout, using frozen weights."""

import numpy as np
import torch
from binding_model import read_packet, tensor
from binding_online import trial
from completion_context import native
from first_parent import records
from partner_index import prepare, conditional, noise
from partner_index_trials import policy
from partner_index_worlds import args, folder, frozen, cases
from selective_trials import inputs


@torch.no_grad()
def evaluate(a):
    rows = []
    for seed in a.seeds:
        m = frozen(a, seed)
        for c in cases():
            mode, n, i, f = c
            z = read_packet(folder(a, c) / "binding.pkl")
            gold = z["gold"]
            data = inputs(z, False)
            future, edges = prepare(m, data)
            r = gold[0][0]
            pr = float((future[0] + m.local.root_prior(data[0])).softmax(-1)[0, r])
            u = noise(np.random.default_rng([seed, i, f, 214]), 4096, 1)[:, :, 0]
            parent = tensor(np.full((1, 4096), r, np.int64))
            ix, reads = conditional(
                edges[0], parent, u, "shared-score", m.local.strength
            )
            sample = ix[0].cpu().numpy()
            prob = np.isin(sample, [b for _, b in gold]).mean()
            rows.append(
                dict(
                    mode=mode,
                    n=n,
                    i=i,
                    flip=f,
                    seed=seed,
                    draws=len(sample),
                    first=pr,
                    second=prob,
                    complete=pr * prob,
                    mean_distinct_reads=np.mean(
                        [
                            len(np.unique(p))
                            for p in reads[0].cpu().numpy().reshape(128, -1)
                        ]
                    ),
                )
            )
        records(a.out / "shared-snapshot.csv", rows)


@torch.no_grad()
def live(a):
    models = {s: frozen(a, s) for s in a.seeds}
    rows = []
    for c in cases():
        mode, n, i, f = c
        seed = a.seeds[(i - 511000) % len(a.seeds)]
        d = folder(a, c)
        ref = native(a, d, "reference", "-")["state_sha"]
        goal = 8 if mode == "multi" else 1
        budgets = [1, 32] if mode == "hard" else [4, 16, 32, 128]
        for budget in budgets:
            if budget != 1 and i != 511000:
                continue
            paired = budget == 32 and mode == "hard"
            arms = ("linear", "shared-score") if paired else ("shared-score",)
            for block in range(2 if paired else 1):
                for arm in arms if (block + i + f) % 2 == 0 else reversed(arms):
                    row = trial(
                        a,
                        d,
                        arm,
                        models[seed],
                        seed,
                        address_seed=93007 + i * 32771 + f + seed,
                        generate=policy(models[seed], arm, seed, i, f, budget),
                    )
                    assert bool(row["graph"] == ref) == (row["ops"] == goal)
                    row.pop("receipts")
                    rows.append(
                        dict(
                            row,
                            n=n,
                            mode=mode,
                            i=i,
                            flip=f,
                            block=block,
                            coverage=row["ops"] / goal,
                        )
                    )
        records(a.out / "shared-online.csv", rows)
    print("shared online", len(rows), flush=True)


if __name__ == "__main__":
    a = args()
    torch.set_num_threads(1)
    (evaluate if a.task == "evaluate" else live)(a)
