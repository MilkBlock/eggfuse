"""Compare ordering of exactly the same minibatches of native Next Cell targets."""

import hashlib
import shutil
from pathlib import Path
from time import perf_counter

import numpy as np
import torch

from address_scores import weight
from completion_context import SIZES, VARIANTS, directory, write
from discovery_states import cli
from next_cell_train import combine, read
from query_fit import batch


def cohort(a, n, held):
    blocks = [
        read(directory(a, n, v, i, p) / "packet.pkl.gz")
        for v in VARIANTS
        for i in (range(80, 82) if held else range(12))
        for p in ((0, 1) if held else (i % 2,))
    ]
    counts = np.array([len(b["offsets"]) - 1 for b in blocks])
    return combine(blocks), np.r_[0, counts.cumsum()]


def schedule(arm, count, seed):
    rng = np.random.default_rng(seed)
    stages = [[] for _ in SIZES]
    for size in range(len(SIZES)):
        for j in range(count):
            stage = size
            if arm == "C" and j >= count // 2 and size < 7:
                stage = int(rng.integers(size + 1, 8))
            stages[stage].append((size, j))
    if arm == "A":
        flat = [x for stage in stages for x in stage]
        rng.shuffle(flat)
        return [flat[k : k + count] for k in range(0, len(flat), count)]
    for stage in stages:
        rng.shuffle(stage)
    return stages


@torch.no_grad()
def probe(net, held):
    result = []
    for s, offsets in held:
        ids = np.arange(offsets[-1])
        chunks = [
            batch(net, s, part, "mps")
            for part in np.array_split(ids, 1 + len(ids) // 192)
        ]
        logp = torch.cat([x.logsumexp(1) for x, _ in chunks]).cpu().numpy()
        factors = torch.cat([f for _, f in chunks]).cpu().numpy()
        rows = []
        for lo, hi in zip(offsets[:-1], offsets[1:]):
            p = np.exp(logp[lo:hi]).astype(float)
            rows.append(
                dict(
                    mass=float(sum(p)),
                    ce=float(-logp[lo:hi].mean()),
                    recall16=float(
                        (-np.expm1(16 * np.log1p(-p.clip(max=1 - 1e-15)))).mean()
                    ),
                    factors=factors[lo:hi].mean(0).tolist(),
                )
            )
        result.append(rows)
    return result


def train(a):
    train = [cohort(a, n, False) for n in SIZES]
    held = [cohort(a, n, True) for n in SIZES]
    for seed in a.seeds:
        dest = a.out / "weights" / str(seed)
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(a.initial, dest / "initial.pt")
        rng = np.random.default_rng(seed)
        draws = []
        for _, ends in train:
            states = rng.integers(len(ends) - 1, size=(a.updates, a.batch))
            draws.append(rng.integers(ends[states], ends[states + 1]))
        for arm in a.arms:
            start = perf_counter()
            net = weight(a).to("mps")
            net.load_state_dict(torch.load(a.initial, weights_only=True))
            opt = torch.optim.AdamW(net.parameters(), lr=0.00015, weight_decay=0)
            curves = []
            steps = 0
            for stage, blocks in enumerate(schedule(arm, a.updates, seed)):
                losses = []
                for size, j in blocks:
                    logp = batch(net, train[size][0], draws[size][j], "mps")[
                        0
                    ].logsumexp(1)
                    loss = -logp.mean()
                    opt.zero_grad()
                    loss.backward()
                    torch.nn.utils.clip_grad_norm_(net.parameters(), 5)
                    opt.step()
                    losses.append(loss.detach())
                steps += len(blocks)
                row = dict(
                    stage=stage,
                    steps=steps,
                    exposures=steps * a.batch,
                    by_size=np.bincount([n for n, _ in blocks], minlength=8).tolist(),
                    train_ce=float(torch.stack(losses).mean()),
                    held=probe(net, held),
                    seconds=perf_counter() - start,
                )
                if stage == 0 and arm == "B":
                    torch.save(
                        {k: v.cpu() for k, v in net.state_dict().items()},
                        dest / "small.pt",
                    )
                curves.append(row)
                print(seed, arm, stage, steps, row["train_ce"], flush=True)
            torch.save(net.cpu().state_dict(), dest / f"{arm}.pt")
            write(
                dest / f"{arm}.json",
                dict(
                    seed=seed,
                    arm=arm,
                    parameters=sum(p.numel() for p in net.parameters()),
                    snapshot_order="variant, instance 80/81, permutation 0/1",
                    draws_sha256=hashlib.sha256(np.stack(draws).tobytes()).hexdigest(),
                    targets_seen=[len(np.unique(d)) for d in draws],
                    curves=curves,
                ),
            )


if __name__ == "__main__":
    p = cli()
    p.add_argument("--initial", type=Path, required=True)
    p.add_argument("--seeds", type=int, nargs="+", default=[9633, 5003, 1777])
    p.add_argument("--arms", nargs="+", default=list("ABC"))
    p.add_argument("--updates", type=int, default=96, help="minibatches per size")
    p.add_argument("--batch", type=int, default=64)
    torch.set_num_threads(1)
    train(p.parse_args())
