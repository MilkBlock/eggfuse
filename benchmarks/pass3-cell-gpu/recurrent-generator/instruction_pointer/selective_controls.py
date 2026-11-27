"""Held-out near misses, effective sparse vocabulary width, and pre-training controls."""

from concurrent.futures import ThreadPoolExecutor
import numpy as np
import torch
from binding_model import read_packet, tensor
from binding_worlds import build
from binding_packets import packet
from first_parent import records
from joint_partner_worlds import world
from selective_kernel import Selective, net
from selective_trials import inputs
from selective_worlds import args, path


def near(a, n, i, f):
    d = a.out / "worlds/near" / f"{n:04}-two-{i:05}-{f}"
    build(
        a,
        ("near", i, n, "two", f, False, False),
        override=world(i, n, "two", f, True, near=True),
    )
    return d


@torch.no_grad()
def run(a):
    sizes = (32, 256, 1024, 4096, 8192)
    jobs = [(n, 300001 + k * 8, f) for n in sizes for k in (0, 1) for f in (0, 1)]
    with ThreadPoolExecutor(4) as pool:
        ds = list(pool.map(lambda q: near(a, *q), jobs))
    for d in ds:
        packet(a, d)
    rows = []
    for seed in a.seeds:
        models = {
            arm: (Selective(a, seed, arm).to("mps").eval(), net(a, seed, arm))
            for arm in ("joint-sparse", "mixed-sparse")
        }
        for (n, i, f), d in zip(jobs, ds):
            for domain, place in [
                ("near", d),
                ("previous", path(a, ("square", n, "two", i, f))),
            ]:
                z = read_packet(place / "binding.pkl")
                (goal,) = z["gold"]
                inp = inputs(z, False)
                y = tensor(np.array([[goal]]))
                variants = []
                for arm, (frozen, trained) in models.items():
                    variants.append((arm, "init", frozen, 262144))
                    variants.extend(
                        (arm, "trained", trained, r) for r in (1024, 16384, 262144)
                    )
                for arm, mode, m, res in variants:
                    m.mapping.resolution = res
                    ps, _ = m(inp, teacher=y)
                    pp = [float(lp[0, 0, j].exp()) for lp, j in zip(ps, goal)]
                    rows.append(
                        dict(
                            n=n,
                            i=i,
                            f=f,
                            seed=seed,
                            arm=arm,
                            mode=mode,
                            res=res,
                            domain=domain,
                            first=pp[0],
                            second=pp[1],
                            complete=np.prod(pp),
                        )
                    )
        records(a.out / "controls.csv", rows)
        print(seed, len(rows), flush=True)


if __name__ == "__main__":
    torch.set_num_threads(1)
    run(args())
