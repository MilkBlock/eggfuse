"""Named-request replay diagnostics and separate no-Cartesian independent CCP runs."""

from collections import defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory
import numpy as np
import torch
from binding_model import collate, read_packet, tensor
from binding_online import trial
from completion_context import native, read, write
from discrete_draft import Cell
from discovery_score import packet
from first_parent import ARMS, load, records


def free_replay(a, d, z, choices, tmp):
    prefix = read(d / "prefix.json")
    start = max((c["token"] for c in prefix["requests"]), default=0) + 1
    cells = [
        Cell(z["rule"], tuple(z["addrs"][j][i] for j, i in enumerate(pair)))
        for pair in choices
    ]
    tape = tmp / "choices.json"
    write(
        tape,
        dict(
            prefix,
            requests=prefix["requests"]
            + [packet(c, 2, start + i) for i, c in enumerate(cells)],
        ),
    )
    rep = native(a, d, "replay", tape, 2, "--ept-origins")
    return sum(g for i, g in rep["ept"]["origins"] if i >= start), rep["counts"].get(
        "rejected", {}
    )


@torch.no_grad()
def evaluate(a, tmp):
    root = a.previous_binding / "worlds"
    paths = sorted(
        [
            p
            for folder in [
                "test",
                "cross-guard",
                *[f"density-{n}" for n in (4, 8, 16, 32, 64)],
            ]
            for p in (root / folder).glob("*/binding.pkl")
            if p.parent.name.split("-")[1] in ("eq10", "eq02", "eq21", "two", "guard")
        ]
    )
    rows = []
    for seed in a.seeds:
        models = {arm: load(a, seed, arm) for arm in ARMS}
        for path in paths:
            z = read_packet(path)
            inp = collate([z])
            gold = list(map(tuple, z["gold"]))
            y = tensor(np.array([gold]))
            valid = set(gold)
            by_root = defaultdict(set)
            for i, j in gold:
                by_root[i].add(j)
            u = tensor(
                np.random.default_rng(seed + z["instance"])
                .random((1, 32, 2))
                .astype(np.float32)
            )
            n = len(z["addrs"][0])
            for arm, net in models.items():
                if arm == "joint" and n > 32:
                    continue
                ps, _ = net(inp, y)
                r = ps[0][0, 0].exp()
                first = float(r[list(by_root)].sum())
                second = np.mean(
                    [
                        float(
                            ps[1][0, next(k for k, x in enumerate(gold) if x[0] == i)]
                            .exp()[list(js)]
                            .sum()
                        )
                        for i, js in by_root.items()
                    ]
                )
                full = (
                    sum(p.gather(-1, y[:, :, j, None]) for j, p in enumerate(ps))
                    .exp()
                    .sum()
                    .item()
                )
                _, draw = net(inp, draws=32, noise=u)
                choices = list(map(tuple, draw[0].cpu().tolist()))
                ops, reject = free_replay(a, path.parent, z, choices, tmp)
                assert ops == len(valid.intersection(choices)), (path, ops, choices)
                row = dict(
                    seed=seed,
                    arm=arm,
                    split=z["split"],
                    layout=z["layout"],
                    size=z["size"],
                    domain=n,
                    instance=z["instance"],
                    order=z["order"],
                    goals=len(valid),
                    first=first,
                    second=second,
                    full=full,
                    hit=sum(ix in valid for ix in choices) / 32,
                    recall32=ops / len(valid),
                    ops=ops,
                    paid=32,
                    guard_reject=reject.get("guard", 0),
                    top1=int(int(r.argmax()) in by_root),
                    prior_mass="",
                    normalized_mass="",
                    energy_gap="",
                    reverse_error="",
                )
                if arm == "joint":
                    logits = net.relation(inp, torch.arange(n, device="mps")[None])[0]
                    prior = net.root_prior(inp)[0]
                    joint = prior[:, None] + logits
                    wrong = sorted(set(range(n)) - set(by_root))
                    row.update(
                        prior_mass=float(prior.exp()[list(by_root)].sum()),
                        normalized_mass=float(
                            (prior + logits.log_softmax(-1).logsumexp(-1))
                            .softmax(0)[list(by_root)]
                            .sum()
                        ),
                        energy_gap=float(
                            logits.logsumexp(-1)[list(by_root)].mean()
                            - logits.logsumexp(-1)[wrong].mean()
                        )
                        if wrong
                        else "",
                        reverse_error=float(
                            (
                                joint.flatten().softmax(0).view_as(joint)
                                - joint.logsumexp(0).softmax(0)[None] * joint.softmax(0)
                            )
                            .abs()
                            .max()
                        ),
                    )
                rows.append(row)
        records(a.out / "snapshots.csv", rows)
        print("snapshots", seed, len(rows), flush=True)


def live(a):
    rows = []
    for seed in a.seeds:
        models = {arm: load(a, seed, arm) for arm in ("field", "pool")}
        for size in (4, 8, 16, 32, 64, 128, 256, 1024):
            for instance in (20000, 20001, 20002):
                d = a.previous_binding / "worlds/test" / f"{size:04}-eq10-{instance}-0"
                goal = len(read(d / "ok.json")["gold"])
                ref = native(a, d, "capture", a.out / "reference-tape.json")[
                    "state_sha"
                ]
                for block in (0, 1):
                    for arm in (
                        ["random", "field", "pool"]
                        if not block
                        else ["pool", "field", "random"]
                    ):
                        row = trial(a, d, arm, models.get(arm), seed)
                        row.update(
                            block=block,
                            instance=instance,
                            goals=goal,
                            coverage=row["ops"] / goal,
                            exact=row["graph"] == ref,
                        )
                        assert row["exact"] == (row["ops"] == goal)
                        row.pop("receipts")
                        rows.append(row)
        records(a.out / "live.csv", rows)
        print("live", seed, len(rows), flush=True)


def run(a):
    if a.task == "eval":
        with TemporaryDirectory() as t:
            evaluate(a, Path(t))
    elif a.task == "live":
        live(a)
    else:
        from first_parent_guard import guard

        guard(a)
