"""Fixed-width replication in unseen 8K native contexts, and observed MPS live tensor bytes."""

from concurrent.futures import ThreadPoolExecutor
import numpy as np
import torch
from torch.utils._python_dispatch import TorchDispatchMode
from binding_model import read_packet, tensor
from binding_packets import packet
from binding_worlds import build
from first_parent import records
from joint_partner_worlds import world
from selective_kernel import ARMS, net, pack
from selective_worlds import args, path
from selective_trials import inputs, issue
from binding_online import trial
from completion_context import native


def jobs(a):
    for domain in ("fresh", "fresh-near"):
        for i in range(511000, 511012):
            for f in (0, 1):
                c = (domain, 8192, "two", i, f)
                yield c, path(a, c)


def prepare(a):
    def one(job):
        c, d = job
        domain, n, kind, i, f = c
        if not (d / "ok.json").exists():
            build(
                a,
                (domain, i, n, kind, f, False, False),
                override=world(i, n, kind, f, True, near=domain.endswith("near")),
            )

    with ThreadPoolExecutor(4) as pool:
        list(pool.map(one, jobs(a)))
    for c, d in jobs(a):
        packet(a, d)


@torch.no_grad()
def evaluate(a):
    rows = []
    for seed in a.seeds:
        models = {
            arm: net(a, seed, arm) for arm in ("wide", "joint-sparse", "mixed-sparse")
        }
        for c, d in jobs(a):
            domain, n, kind, i, f = c
            z = read_packet(d / "binding.pkl")
            (gold,) = z["gold"]
            y = tensor(np.array([[gold]]))
            for cp in (0, 1):
                data = inputs(z, cp)
                for arm, m in models.items():
                    ps, _ = m(data, teacher=y)
                    pp = [float(lp[0, 0, j].exp()) for lp, j in zip(ps, gold)]
                    rows.append(
                        dict(
                            seed=seed,
                            domain=domain,
                            i=i,
                            f=f,
                            copy=cp,
                            arm=arm,
                            first=pp[0],
                            second=pp[1],
                            complete=np.prod(pp),
                            rank=1 + int((ps[0][0, 0] > ps[0][0, 0, gold[0]]).sum()),
                        )
                    )
        records(a.out / "replication.csv", rows)


@torch.no_grad()
def live(a):
    rows = []
    models = {
        (s, arm): net(a, s, arm) for s in a.seeds for arm in ("wide", "mixed-sparse")
    }
    for c, d in jobs(a):
        domain, n, _, i, f = c
        seed = a.seeds[(i - 511000) % len(a.seeds)]
        addr = 93007 + i * 32771 + f + seed
        reference = native(a, d, "reference", "-")["state_sha"]
        arms = ("wide", "mixed-sparse")
        for arm in arms if (i + f) % 2 == 0 else reversed(arms):
            m = models[seed, arm]
            row = trial(
                a,
                d,
                arm,
                m,
                seed,
                address_seed=addr,
                generate=issue(m, False, 1, [seed, i, f, 81]),
            )
            assert row["paid"] == 1 and bool(row["ops"]) == (row["graph"] == reference)
            row.pop("receipts")
            rows.append(
                dict(
                    row,
                    domain=domain,
                    i=i,
                    flip=f,
                    address_seed=addr,
                    reference=reference,
                )
            )
        records(a.out / "fresh-online.csv", rows)


class AllocationTrace(TorchDispatchMode):
    def __init__(self):
        super().__init__()
        self.initial = torch.mps.current_allocated_memory()
        self.peak = self.initial
        self.calls = 0

    def __torch_dispatch__(self, func, types, args=(), kwargs=None):
        v = func(*args, **(kwargs or {}))
        self.peak = max(self.peak, torch.mps.current_allocated_memory())
        self.calls += 1
        return v


@torch.no_grad()
def memory(a):
    rows = []
    for seed in a.seeds[:1]:
        for n in (1024, 4096, 8192):
            z = read_packet(path(a, ("square", n, "two", 300001, 0)) / "binding.pkl")
            data = pack([z])
            u = tensor(
                np.random.default_rng(seed).random((1, 32, 2)).astype(np.float32)
            )
            for arm in ARMS:
                m = net(a, seed, arm)
                for component, call in [
                    ("messages", lambda: m.flow(*data)),
                    ("page", lambda: m(data, noise=u)),
                ]:
                    torch.mps.synchronize()
                    with AllocationTrace() as t:
                        call()
                    torch.mps.synchronize()
                    rows.append(
                        dict(
                            n=n,
                            arm=arm,
                            component=component,
                            dispatches=t.calls,
                            peak_live_bytes_above_baseline=t.peak - t.initial,
                        )
                    )
    records(a.out / "mps-memory.csv", rows)


if __name__ == "__main__":
    a = args()
    torch.set_num_threads(1)
    {"prepare": prepare, "evaluate": evaluate, "cost": memory, "live": live}[a.task](a)
