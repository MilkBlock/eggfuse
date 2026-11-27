"""Independent CCP and frozen named-state evaluation. No exact labels in online generation."""

import hashlib
from itertools import product
import numpy as np
import torch
from binding_model import read_packet, tensor
from binding_online import trial
from completion_context import native
from discrete_draft import Cell
from credit_scale_buffer import submit
from first_parent import records
from selective_kernel import ARMS, net, pack
from selective_worlds import args, cases, path


def inputs(z, copy_on):
    return pack(
        [z if copy_on else dict(z, banks=[dict(b, last=-1) for b in z["banks"]])]
    )


@torch.no_grad()
def frozen(a):
    rows = []
    for seed in a.seeds:
        models = {arm: net(a, seed, arm) for arm in ARMS}
        for c in cases():
            side, n, kind, i, f = c
            z = read_packet(path(a, c) / "binding.pkl")
            y = tensor(np.array([z["gold"]]))
            u = tensor(
                np.random.default_rng([seed, i, n, f])
                .random((1, 32, y.shape[-1]))
                .astype(np.float32)
            )
            for cp in (0, 1):
                data = inputs(z, cp)
                for arm, m in models.items():
                    future = m.flow(*data)
                    ps, _ = m.draw(data, future, y, None)
                    _, ix = m.draw(data, future, None, u)
                    p = [float(lp[0, 0, k].exp()) for lp, k in zip(ps, z["gold"][0])]
                    rows.append(
                        dict(
                            side=side,
                            n=n,
                            kind=kind,
                            i=i,
                            flip=f,
                            seed=seed,
                            arm=arm,
                            copy=cp,
                            first=p[0],
                            second=p[1],
                            complete=np.prod(p),
                            third=p[2] if len(p) > 2 else "",
                            hits=int((ix == y).all(-1).sum()),
                            root_rank=1
                            + int((ps[0][0, 0] > ps[0][0, 0, z["gold"][0][0]]).sum()),
                        )
                    )
        records(a.out / "frozen.csv", rows)
        print("frozen", seed, len(rows), flush=True)


def issue(m, copy_on, slots, rng_seed):
    def propose(client, z, program, rng):
        rng = np.random.default_rng(rng_seed)
        u = tensor(rng.random((1, slots, len(z["banks"]))).astype(np.float32))
        _, ix = m(inputs(z, copy_on), noise=u)
        cells = [
            Cell(z["rule"], tuple(z["addrs"][j][p] for j, p in enumerate(sel)))
            for sel in ix[0].cpu().tolist()
        ]
        submit(client, cells, 32)
        return len(cells)

    return propose


def identity(z):
    h = hashlib.sha256()
    for refs, b in zip(z["addrs"], z["banks"]):
        order = sorted(range(len(refs)), key=refs.__getitem__)
        h.update(np.asarray([refs[k] for k in order], dtype=np.int64).tobytes())
        h.update(b["hash"][order].tobytes())
    return h.hexdigest()


@torch.no_grad()
def live(a, extra=False):
    rows = []
    for seed in a.seeds:
        models = {arm: net(a, seed, arm) for arm in ARMS}
        suite = (
            [
                ("near", n, "two", 300001, f)
                for n in (256, 1024, 4096, 8192)
                for f in (0, 1)
            ]
            if extra
            else cases()
        )
        for c in suite:
            side, n, kind, i, f = c
            if (
                side not in ("square", "near")
                or (kind == "two" and (i != 300001 or n == 128))
                or (kind != "two" and n not in (256, 1024))
            ):
                continue
            d = path(a, c)
            ref = native(a, d, "reference", "-")["state_sha"]
            # Physical assignment in the native executor. Never use a teacher tape online.
            addr = 73007 + i * 32771 + f
            if seed != a.seeds[0]:
                addr += seed * 13
            if seed == a.seeds[0]:
                observed = []

                def check(client, z, program, rng):
                    observed.append(identity(z))
                    return 0

                trial(
                    a, d, "address-audit", None, seed, generate=check, address_seed=addr
                )
                assert observed == [identity(read_packet(d / "binding.pkl"))]
            jobs = list(
                product(
                    ("wide", "joint-sparse", "mixed-sparse") if extra else ARMS, (0, 1)
                )
            ) + [("random", 0)]
            for block in (0, 1):
                for arm, cp in jobs if block == 0 else reversed(jobs):
                    policy = (
                        issue(models[arm], cp, 32, [seed, n, i, f])
                        if arm != "random"
                        else None
                    )
                    row = trial(
                        a,
                        d,
                        arm,
                        models.get(arm),
                        seed,
                        generate=policy,
                        address_seed=addr,
                    )
                    assert row["paid"] == 32 and (row["graph"] == ref) == bool(
                        row["ops"]
                    )
                    row.pop("receipts")
                    rows.append(
                        dict(
                            row,
                            kind=kind,
                            n=n,
                            i=i,
                            flip=f,
                            copy=cp,
                            block=block,
                            address_seed=addr,
                            reference=ref,
                        )
                    )
            records(a.out / ("near-online.csv" if extra else "online.csv"), rows)
        print("online", seed, len(rows), flush=True)


if __name__ == "__main__":
    a = args()
    torch.set_num_threads(1)
    if a.task == "live":
        live(a, extra=a.near)
    else:
        frozen(a)
