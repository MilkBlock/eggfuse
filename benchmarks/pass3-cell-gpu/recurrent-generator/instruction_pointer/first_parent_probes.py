"""Offline native split-witness intervention and calibration before joint training."""

import random
import numpy as np
import torch
from binding_model import collate, read_packet, tensor
from binding_packets import packet
from binding_worlds import build
from first_parent import FirstParent, load, records, options
from first_parent_trials import free_replay
from pathlib import Path
from tempfile import TemporaryDirectory


def split_world(a, i, p):
    # Alpha names fixed within each intervention pair. Unique random fillers ensure
    # each of the decoy's two outstanding equalities has a different witness.
    rng = random.Random(i)
    v = rng.sample(range(10**13, 10**14), 24)
    rows = np.array(v).reshape(8, 3)
    rows[1, 2], rows[1, 0] = rows[0, 1], rows[0, 2]
    rows[3, 2], rows[4, 0] = rows[2, 1], rows[2, 2]
    decoy = int(rows[2, 0])
    src = [
        "(relation Edge (i64 i64 i64))",
        "(relation Result (i64 i64))",
        "(ruleset warm)",
        "(ruleset probe)",
        "(rule ((Edge x y z) (Edge z k y)) ((Result x k)) :ruleset probe)",
    ]
    order = list(range(8))
    random.Random(i + 391 * p).shuffle(order)
    src.extend("(Edge %d %d %d)" % tuple(rows[j]) for j in order)
    job = ("split-witness", i, 8, "two", p, False, False)
    build(
        a,
        job,
        override="\n".join([*src, "(run-schedule (run warm) (run probe))"]) + "\n",
    )
    d = a.out / "worlds/split-witness" / f"0008-two-{i}-{p}"
    packet(a, d)
    z = read_packet(d / "binding.pkl")
    assert len(z["gold"]) == 1
    [idx] = np.flatnonzero(z["banks"][0]["raw"][:, 0] == decoy)
    return d, z, int(idx)


@torch.no_grad()
def probes(a, tmp):
    fixtures = [split_world(a, 110000 + i, p) for i in range(12) for p in (0, 1)]
    rows = []
    cal = []
    for seed in a.seeds:
        nets = {arm: load(a, seed, arm) for arm in ("field", "joint", "pool")}
        for d, z, decoy in fixtures:
            inp = collate([z])
            y = tensor(np.array([z["gold"]]))
            for arm, net in nets.items():
                probs, _ = net(inp, y)
                u = tensor(
                    np.random.default_rng(z["instance"] + seed)
                    .random((1, 32, 2))
                    .astype(np.float32)
                )
                _, ix = net(inp, draws=32, noise=u)
                choices = list(map(tuple, ix[0].cpu().tolist()))
                new, reject = free_replay(a, d, z, choices, tmp)
                r, s = z["gold"][0]
                assert new == int((r, s) in choices) and decoy != r
                rows.append(
                    dict(
                        seed=seed,
                        instance=z["instance"],
                        permutation=z["order"],
                        arm=arm,
                        real=float(probs[0][0, 0, r].exp()),
                        split=float(probs[0][0, 0, decoy].exp()),
                        hit=choices.count((r, s)) / 32,
                        ops=new,
                    )
                )
        models = {
            "original-C": FirstParent(a, seed, "joint").to("mps"),
            "CE-field": nets["field"],
            "CE-joint": nets["joint"],
        }
        for p in sorted(
            (a.previous_binding / "worlds/test").glob("*-eq*-*-*/binding.pkl")
        ):
            z = read_packet(p)
            if z["size"] > 32:
                continue
            inp = collate([z])
            ids = torch.arange(z["size"], device="mps")[None]
            roots = sorted({q[0] for q in z["gold"]})
            for label, net in models.items():
                energy = net.relation(inp, ids)[0]
                prior = net.root_prior(inp)[0]
                renorm = energy.log_softmax(1).logsumexp(1)
                cal.append(
                    dict(
                        seed=seed,
                        model=label,
                        size=z["size"],
                        instance=z["instance"],
                        layout=z["layout"],
                        order=z["order"],
                        raw=float(
                            (prior + energy.logsumexp(1)).softmax(0)[roots].sum()
                        ),
                        conditional_only=float(
                            (prior + renorm).softmax(0)[roots].sum()
                        ),
                        prior=float(prior.exp()[roots].sum()),
                    )
                )
    records(a.out / "split-witness.csv", rows)
    records(a.out / "calibration.csv", cal)


if __name__ == "__main__":
    a = options().parse_args()
    torch.set_num_threads(1)
    with TemporaryDirectory() as t:
        probes(a, Path(t))
