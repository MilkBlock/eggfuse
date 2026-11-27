"""Separate dilution on the partner side from normalization on the root side."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
import numpy as np
import torch
from binding_model import tensor, read_packet
from binding_packets import packet
from binding_worlds import build
from first_parent import records
from first_parent_trials import free_replay
from joint_partner import model, batch
from joint_partner_worlds import options, folder, world
from joint_partner_eval import diagnostic


def suite():
    for n in (4, 64, 256, 1024):
        for side, counts in [("left", (n, 4)), ("right", (4, n))]:
            for k in range(3):
                for flip in (0, 1):
                    yield (side, 300001 + 8 * k, n, "two", flip, True), counts


def prepare(a):
    def make(item):
        job, counts = item
        split, i, n, k, f, held = job
        build(
            a,
            (split, i, n, k, f, False, False),
            override=world(i, n, k, f, held, counts),
        )

    with ThreadPoolExecutor(4) as ex:
        list(ex.map(make, suite()))
    goals = {}
    for job, counts in suite():
        d = folder(a, job)
        packet(a, d)
        z = read_packet(d / "binding.pkl")
        assert [len(b["row"]) for b in z["banks"]] == list(counts)
        (gold,) = z["gold"]
        ident = tuple(tuple(b["raw"][i, :3]) for b, i in zip(z["banks"], gold))
        key = (job[1], job[4])
        assert goals.setdefault(key, ident) == ident


@torch.no_grad()
def evaluate(a, tmp):
    rows = []
    for seed in a.seeds:
        for arm in ("independent", "cell", "tensor", "wide"):
            net = model(a, seed, arm)
            for job, counts in suite():
                d = folder(a, job)
                z = read_packet(d / "binding.pkl")
                inp, layout = batch([z])
                goal = z["gold"][0]
                future, edges = net.messages(inp, layout)
                ps, _ = net.decode(inp, future, edges, tensor(np.array([[goal]])), None)
                u = tensor(
                    np.random.default_rng(seed + job[1] + 1009 * job[4])
                    .random((1, 32, 2))
                    .astype(np.float32)
                )
                _, refs = net.decode(inp, future, edges, None, u)
                choices = list(map(tuple, refs[0].cpu().tolist()))
                ops, _ = free_replay(a, d, z, choices, tmp)
                hits = choices.count(tuple(goal))
                assert ops == int(hits > 0)
                p, q = [float(v[0, 0, i].exp()) for v, i in zip(ps, goal)]
                rows.append(
                    dict(
                        seed=seed,
                        arm=arm,
                        roots=counts[0],
                        partners=counts[1],
                        side=job[0],
                        instance=job[1],
                        flip=job[4],
                        first=p,
                        second=q,
                        complete=p * q,
                        hits=hits,
                        **diagnostic(net, inp, layout, future, goal),
                    )
                )
    records(a.out / "stress.csv", rows)


if __name__ == "__main__":
    a = options().parse_args()
    torch.set_num_threads(1)
    if a.task == "prepare":
        prepare(a)
    else:
        with TemporaryDirectory() as t:
            evaluate(a, Path(t))
