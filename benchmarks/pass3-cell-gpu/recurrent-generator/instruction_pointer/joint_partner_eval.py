"""Common-random-number free sampling, native per-page replay and online trials."""

from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
import numpy as np
import torch
import binding_model
from binding_model import tensor, read_packet
from binding_online import trial
from completion_context import native
from credit_scale_buffer import submit
from discrete_draft import Cell
from first_parent import records
from first_parent_trials import free_replay
from joint_partner_worlds import ARMS, jobs, folder
from joint_partner import batch, edge_view, model


def diagnostic(net, inp, layout, future, indices):
    e = edge_view(inp, 0)
    root = indices[0]
    partner = indices[1]
    logits = (net.local.root_prior(inp) + future[0])[0]
    other = torch.arange(len(logits), device=logits.device) != root
    logz_bad = logits[other].logsumexp(0)
    out = dict(
        prior=float(net.local.root_prior(inp)[0, root].exp()),
        gap=float(logits[root] - logits[other].max()),
        root_rank=1 + int((logits > logits[root]).sum()),
        wrong_log_partition_minus_right=float(logz_bad - logits[root]),
        true_kernel="",
        wrong_kernel_sum="",
        wrong_kernel_max="",
        summary_bytes="",
    )
    if net.arm == "dense":
        return out
    left, right = net.features(e, layout[0])
    truth = left[:, root : root + 1]
    # Only the offline diagnostic compares the annotated root with this bank.
    # Sum in physical order; no alias lookup or Cartesian scoring in generation.
    if net.arm == "independent":
        scores = torch.einsum(
            "bfhk,bnghk,bfg->bnh", truth[:, 0], right, net.local.role_attention(e)
        )
    else:
        scores = torch.einsum("bhk,bnhk->bnh", truth[:, 0], right)
    scores = scores.mean(-1)[0]
    mask = torch.arange(len(scores), device=scores.device) != partner
    out.update(
        true_kernel=float(scores[partner]),
        wrong_kernel_sum=float(scores[mask].sum()),
        wrong_kernel_max=float(scores[mask].max()),
        summary_bytes=right[0, 0].numel() * right.element_size(),
    )
    return out


@torch.no_grad()
def evaluate(a, tmp):
    rows = []
    for seed in a.seeds:
        nets = {k: model(a, seed, k) for k in ARMS}
        for job in jobs():
            split, i, n, kind, flip, _ = job
            if split != "held":
                continue
            d = folder(a, job)
            z = read_packet(d / "binding.pkl")
            goal = z["gold"][0]
            y = tensor(np.array([[goal]]))
            inp, layout = batch([z])
            noise = tensor(
                np.random.default_rng(seed + i + 1009 * flip)
                .random((1, 32, len(goal)))
                .astype(np.float32)
            )
            for arm, net in nets.items():
                if arm == "dense" and n > 32:
                    continue
                future, tables = net.messages(inp, layout)
                ps, _ = net.decode(inp, future, tables, y, None)
                pp = [float(p[0, 0, addr].exp()) for p, addr in zip(ps, goal)]
                _, picks = net.decode(inp, future, tables, None, noise)
                choices = list(map(tuple, picks[0].cpu().tolist()))
                ops, rejected = free_replay(a, d, z, choices, tmp)
                hits = choices.count(tuple(goal))
                assert ops == int(hits > 0)
                rows.append(
                    dict(
                        seed=seed,
                        size=n,
                        kind=kind,
                        instance=i,
                        flip=flip,
                        arm=arm,
                        first=pp[0],
                        second=pp[1],
                        third=pp[2] if len(pp) == 3 else "",
                        complete=np.prod(pp),
                        top1_all=int(
                            all(
                                int(p[0, 0].argmax()) == addr
                                for p, addr in zip(ps, goal)
                            )
                        ),
                        hits=hits,
                        ops=ops,
                        paid=32,
                        **diagnostic(net, inp, layout, future, goal),
                    )
                )
        records(a.out / "snapshot-trials.csv", rows)
        print("snapshot", seed, len(rows), flush=True)


def generate(net, slots=32):
    if net.arm == "dense":
        raise ValueError("dense path is offline only")

    def issue(client, z, program, rng):
        u = tensor(rng.random((1, slots, len(z["banks"]))).astype(np.float32))
        _, indices = net(batch([z]), noise=u)
        cells = [
            Cell(z["rule"], tuple(z["addrs"][j][r] for j, r in enumerate(refs)))
            for refs in indices[0].cpu().tolist()
        ]
        submit(client, cells, 32)
        return len(cells)

    return issue


def live(a, cpu=False):
    if cpu:
        binding_model.DEVICE = "cpu"
        torch.set_num_interop_threads(1)
    rows = []
    for seed in a.seeds:
        nets = {
            k: model(a, seed, k, "cpu" if cpu else "mps") for k in ARMS if k != "dense"
        }
        for job in jobs():
            split, i, n, kind, flip, _ = job
            if split != "held" or (i - 300000) // 8 >= (1 if cpu else 2):
                continue
            if n not in ((8, 64, 512) if cpu else (4, 16, 32, 64, 256, 512, 1024)):
                continue
            if cpu and kind not in ("two", "chain"):
                continue
            d = folder(a, job)
            ref = native(a, d, "reference", "-")["state_sha"]
            for block in (0, 1):
                arms = ["random", *nets] if not cpu else ["exact", *nets]
                for arm in arms if block == 0 else reversed(arms):
                    if arm == "exact":
                        start = perf_counter()
                        result = native(a, d, "reference", "-")
                        wall = perf_counter() - start
                        row = dict(
                            arm=arm,
                            seed=seed,
                            size=n,
                            paid="",
                            ops=1,
                            seconds=wall,
                            eps=1 / wall,
                            ept="",
                            graph=result["state_sha"],
                        )
                    else:
                        row = trial(
                            a,
                            d,
                            arm,
                            nets.get(arm),
                            seed,
                            generate=generate(nets[arm]) if arm in nets else None,
                        )
                        row.pop("receipts")
                    assert row["ops"] in (0, 1) and (row["graph"] == ref) == bool(
                        row["ops"]
                    )
                    rows.append(
                        dict(
                            row,
                            block=block,
                            kind=kind,
                            instance=i,
                            flip=flip,
                            coverage=row["ops"],
                        )
                    )
        records(a.out / ("cpu.csv" if cpu else "online.csv"), rows)
        print("live", cpu, seed, len(rows), flush=True)


def run(a):
    if a.task == "evaluate":
        with TemporaryDirectory() as tmp:
            evaluate(a, Path(tmp))
    elif a.task == "cost":
        from joint_partner_cost import measure

        measure(a)
    else:
        live(a, a.task == "cpu")
