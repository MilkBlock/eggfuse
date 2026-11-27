"""Held three-way parity with identical pairwise marginals; chain message ablation."""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from itertools import combinations
from pathlib import Path
from tempfile import TemporaryDirectory
import numpy as np
import torch
from binding_model import tensor, read_packet
from binding_packets import packet
from binding_worlds import build
from first_parent import records
from first_parent_trials import free_replay
from joint_partner import model, batch, edge_view
from joint_partner_worlds import options, folder, world, ARMS


def suite():
    for n in (4, 32, 256, 512, 1024):
        for i in range(4):
            for f in (0, 1):
                yield ("parity", 700000 + i, n, "three", f, True)


def validate(A, B):
    for fields in combinations(range(3), 2):
        assert Counter(map(tuple, A[:, fields])) == Counter(map(tuple, B[:, fields]))
    assert set(map(tuple, A[:, :3])) != set(map(tuple, B[:, :3]))


def prepare(a):
    def make(job):
        split, i, n, kind, f, held = job
        build(
            a,
            (split, i, n, kind, f, False, False),
            override=world(i, n, kind, f, held, parity=True),
        )

    with ThreadPoolExecutor(4) as ex:
        list(ex.map(make, suite()))
    for job in suite():
        d = folder(a, job)
        packet(a, d)
        if job[4]:
            other = folder(a, (*job[:4], 0, job[5]))
            u, v = [read_packet(p / "binding.pkl") for p in (other, d)]
            validate(u["banks"][1]["raw"], v["banks"][1]["raw"])
            for z in (u, v):
                assert len(z["gold"]) == 1
            assert not np.array_equal(
                *[z["banks"][0]["raw"][z["gold"][0][0], :3] for z in (u, v)]
            )


@torch.no_grad()
def check(a, tmp):
    rows = []
    chain = [
        ("held", 300003 + 8 * i, n, "chain", f, True)
        for n in (4, 32, 256, 1024)
        for i in range(3)
        for f in (0, 1)
    ]
    for seed in a.seeds:
        for arm in ARMS:
            net = model(a, seed, arm)
            for job in [*suite(), *chain]:
                if arm == "dense" and job[2] > 32:
                    continue
                d = folder(a, job)
                z = read_packet(d / "binding.pkl")
                inp, w = batch([z])
                future, dense = net.messages(inp, w)
                gold = z["gold"][0]
                y = tensor(np.array([[gold]]))
                u = tensor(
                    np.random.default_rng(seed + job[1] + job[4])
                    .random((1, 32, len(gold)))
                    .astype(np.float32)
                )

                def record(mode):
                    ps, _ = net.decode(inp, future, dense, y, None)
                    _, ix = net.decode(inp, future, dense, None, u)
                    choices = list(map(tuple, ix[0].cpu().tolist()))
                    new, _ = free_replay(a, d, z, choices, tmp)
                    hits = choices.count(tuple(gold))
                    assert new == int(hits > 0)
                    p = [float(s[0, 0, j].exp()) for s, j in zip(ps, gold)]
                    rows.append(
                        dict(
                            seed=seed,
                            arm=arm,
                            n=job[2],
                            instance=job[1],
                            flip=job[4],
                            case=job[0],
                            mode=mode,
                            root=p[0],
                            complete=np.prod(p),
                            hits=hits,
                            ops=new,
                        )
                    )

                record("full")
                if job[0] == "held":
                    # Keep all conditional decoders intact. Only remove tail evidence
                    # from the first-parent message, using exactly the same edge scorer.
                    first, _ = net.messages(edge_view(inp, 0), w[:1])
                    future[0] = first[0]
                    record("no-tail-at-root")
        records(a.out / "challenge.csv", rows)
        print(seed, len(rows), flush=True)


if __name__ == "__main__":
    a = options().parse_args()
    torch.set_num_threads(1)
    if a.task == "prepare":
        prepare(a)
    else:
        with TemporaryDirectory() as t:
            check(a, Path(t))
