"""Metal teacher forcing over complete, native-witnessed Cell probabilities."""

import gzip
import json
import pickle
from collections import Counter
from pathlib import Path
from time import perf_counter

import numpy as np
import torch

from address_scores import weight
from discovery_states import cli
from query_fit import batch
from next_cell_corpus import digest


def combine(blocks):
    """Pack several states without sharing address identities across states."""
    count = sum(len(x["paths"]) for x in blocks)
    roles, depth = np.max([x["paths"].shape[1:] for x in blocks], axis=0)
    routes = np.zeros((count, roles, depth), np.int32)
    meta = np.zeros((count, roles, 7), np.float32)
    meta[:, :, 2] = -1
    sizes, features = [], []
    leaf = node = 0
    for x in blocks:
        p = x["paths"]
        n, r, d = p.shape
        routes[leaf : leaf + n, :r, :d] = p + np.sign(p) * node
        meta[leaf : leaf + n, :r] = x["meta"]
        features.append(x["features"])
        leaf += n
        node += len(x["features"])
        sizes.extend(np.diff(x["offsets"]))
        if ((x["meta"][:, :, 6] == 0) & (x["meta"][:, :, 5] > 0)).any():
            raise ValueError("native witness outside the physical decoder domain")
    return dict(
        paths=routes,
        meta=meta,
        features=np.concatenate(features),
        offsets=np.r_[0, np.cumsum(sizes)],
    )


def read(path):
    with gzip.open(path, "rb") as f:
        return pickle.load(f)


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


@torch.no_grad()
def validation(net, states, batch_size):
    losses, distinct = [], []
    for s in states:
        n = len(s["offsets"]) - 1
        logp = torch.cat(
            [
                batch(net, s, np.arange(i, min(n, i + batch_size)), "mps")[0].logsumexp(
                    1
                )
                for i in range(0, n, batch_size)
            ]
        )
        losses.append(-logp)
        # Independent complete attempts; probability missing through failed slots
        # remains missing. This curve is a teacher-forced expectation on known targets.
        distinct.append(-torch.expm1(64 * torch.log1p(-logp.exp().clamp(max=1))))
    return dict(
        held_ce=float(torch.cat(losses).mean()),
        held_expected_recall64=float(torch.cat(distinct).mean()),
    )


def run(a):
    ids = list(range(a.programs)) + list(range(256, 264))
    loaded = [read(a.out / "packets" / f"{i:04}.pkl.gz") for i in ids]
    if {x["signature"] for x in loaded[:-8]} & {x["signature"] for x in loaded[-8:]}:
        raise ValueError("normalized structural leakage")
    counts = Counter()
    for x in loaded[:-8]:
        counts.update(x["counts"])
    cohort = [combine(x["blocks"]) for x in loaded]
    del loaded
    train, held = cohort[:-8], cohort[-8:]
    name = f"ce{len(train)}"
    if a.mixed:
        paths = sorted((a.out / "mixed-teacher").glob("*/*/targets.pkl.gz"))
        if len(paths) != 6:
            raise ValueError("incomplete native teaching tapes")
        for path in paths:
            x = read(path)
            train.append(combine(x["blocks"]))
            counts["supplemental_targets"] += sum(len(b["cells"]) for b in x["blocks"])
            counts["supplemental_higher"] += sum(
                c.higher for b in x["blocks"] for c in b["cells"]
            )
        name += "mixed"
    n = sum(len(s["offsets"]) - 1 for s in train)
    write_json(
        a.out / f"corpus-{name}.json",
        dict(
            counts=counts,
            train_programs=ids[:-8],
            held_programs=ids[-8:],
            initial_sha=digest(a.initial.read_bytes()),
        ),
    )
    for seed in a.seeds:
        rng = np.random.default_rng(seed)
        net = weight(a).to("mps")
        net.load_state_dict(torch.load(a.initial, weights_only=True))
        optimizer = torch.optim.AdamW(net.parameters(), lr=a.lr, weight_decay=0)
        curves = []
        start = perf_counter()
        steps = 0
        exposure = 0
        for epoch in range(a.epochs + 1):
            total = torch.zeros((), device="mps")
            seen = 0
            if epoch:
                for idx in rng.permutation(len(train)):
                    s = train[idx]
                    perm = rng.permutation(len(s["offsets"]) - 1)
                    for i in range(0, len(perm), a.batch):
                        chosen = perm[i : i + a.batch]
                        logp = batch(net, s, chosen, "mps")[0].logsumexp(1)
                        loss = -logp.mean()
                        optimizer.zero_grad()
                        loss.backward()
                        torch.nn.utils.clip_grad_norm_(net.parameters(), 5)
                        optimizer.step()
                        total += loss.detach() * len(chosen)
                        seen += len(chosen)
                        steps += 1
                if seen != n:
                    raise ValueError("incomplete epoch")
                exposure += seen
            score = validation(net, held, a.batch)
            row = dict(
                seed=seed,
                epoch=epoch,
                steps=steps,
                exposures=exposure,
                train_ce=float(total / seen) if seen else None,
                seconds=perf_counter() - start,
                **score,
            )
            if not np.isfinite(score["held_ce"]):
                raise ValueError("nonfinite CE")
            curves.append(row)
            print(name, row, flush=True)
            write_json(a.out / f"curve-{name}-{seed}.json", curves)
        dest = a.out / "weights" / str(seed)
        dest.mkdir(parents=True, exist_ok=True)
        torch.save(net.cpu().state_dict(), dest / (name + ".pt"))


if __name__ == "__main__":
    p = cli()
    p.add_argument("--initial", type=Path, required=True)
    p.add_argument("--programs", type=int, default=200, choices=range(1, 201))
    p.add_argument("--mixed", action="store_true")
    p.add_argument("--epochs", type=int, default=5)
    p.add_argument("--batch", type=int, default=192)
    p.add_argument("--lr", type=float, default=0.00015)
    p.add_argument("--seeds", type=int, nargs="+", default=[9633, 5003])
    torch.set_num_threads(1)
    run(p.parse_args())
