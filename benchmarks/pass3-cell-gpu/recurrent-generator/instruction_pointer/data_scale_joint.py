"""Recompute the existing encoder on live training frames for a matched 10K fine-tune."""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import torch
from torch.nn import functional as F

from discrete_cells import from_q
from discrete_editor import features
from latent_cell_flow import Frozen
from metal_scaling import CASES, execute_one, models, objective
from recursive_train import read
from response_plan import ResponseMemory
from response_study import memory
from ripsat_policy import CellScorer


def contexts(a):
    meta = read(a.out / "corpus.json")[:16]
    # Identical round-robin 10K manifest, independent of any supervision.
    arrays = [
        np.load(a.out / "programs" / f"{r['id']:04d}" / "plans.npy") for r in meta
    ]
    sizes = np.array(list(map(len, arrays)))
    ordered = np.lexsort(
        (
            np.repeat(np.arange(len(sizes)), sizes),
            np.concatenate([np.arange(k) for k in sizes]),
        )
    )[:10000]
    groups = defaultdict(list)
    sources = []
    for i, r in enumerate(meta):
        d = a.out / "programs" / f"{i:04d}"
        start = sizes[:i].sum()
        ix = ordered[(ordered >= start) & (ordered < start + sizes[i])] - start
        prog = read(d / "program.json")
        m = memory(a, d)
        raw = list(map(json.loads, (d / "memory.jsonl").read_text().splitlines()))
        cells = [from_q(q) for q in read(d / "teacher.json")["requests"]]
        sources.append((prog, m.contract, m.menu, raw, cells))
        for run, *ids in arrays[i][ix]:
            groups[i, int(run)].append([int(k) for k in ids if k >= 0])
    return groups, sources


def train(a, groups, sources, arm, seed):
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    root = a.out / f"s{seed}"
    directory = a.out / "fine" / f"s{seed}" / (arm + "-n10000")
    directory.mkdir(parents=True, exist_ok=True)
    if (directory / "fit.json").exists():
        return
    marks, rates = models("100K")
    if arm == "wide_mark":
        marks = models("1M")[0]
    if arm == "wide_rate":
        rates = models("1M")[1]
    for idx, model in enumerate((marks, rates)):
        size = (
            "1M"
            if (idx == 0 and arm == "wide_mark") or (idx == 1 and arm == "wide_rate")
            else "100K"
        )
        model.load_state_dict(
            torch.load(root / (size + "-n10000") / "weights.pt", weights_only=True)[idx]
        )
    from rule_read import load_actor

    actor = load_actor(a.actor, True)
    scorer = CellScorer(32)
    scorer.load_state_dict(
        torch.load(
            "run-recall/parameterized-deep-ripsat/event-gnn.pt", weights_only=True
        )["model"]
    )
    joint = arm == "joint"
    for p in [*actor.parameters(), *scorer.parameters()]:
        p.requires_grad_(joint)
    opt = torch.optim.AdamW(
        [
            p
            for model in (actor, scorer, marks, rates)
            for p in model.parameters()
            if p.requires_grad
        ],
        lr=0.0002,
    )
    legacy, _ = torch.load(a.previous / "large.pt", weights_only=True)
    losslog = []
    total = 0
    for epoch in range(a.epochs):
        batches = []
        for key, values in groups.items():
            for ii in np.array_split(
                rng.permutation(len(values)), max(1, int(np.ceil(len(values) / 32)))
            ):
                batches.append((key, [values[j] for j in ii]))
        rng.shuffle(batches)
        for (i, run), rows in batches:
            prog, ct, menu, frames, cells = sources[i]
            m = ResponseMemory(Frozen(prog, actor, scorer), ct, menu, scorer)
            for f in frames:
                m.update(f)
                if f["run"] == run:
                    break
            ax = []
            ay = []
            aw = []
            rx = []
            ry = []
            rw = []
            vectors = {}
            for row in rows:
                start = int(rng.integers(len(row))) if rng.random() < 0.5 else 0
                n = len(row) - start
                k = rng.integers(n + 1)
                step = int(rng.integers(n))
                y = []
                target = cells[row[start + step]]
                if marks.draw(m, rng, Counter(), target=target, records=y) != target:
                    raise ValueError("binding")
                x, label, _ = y[rng.integers(len(y))]
                ax.append(x)
                ay.append(label)
                aw.append(len(y) * n * (n - step) / (n + 1))
                cur = row[: start + k]
                for j in cur:
                    if j not in vectors:
                        vectors[j] = m.embed(cells[j])
                p = int(rng.integers(len(cur) + 1))
                rx.append(
                    features(
                        m.state,
                        m.event,
                        [vectors[j] for j in cur],
                        rng.beta(k + 1, n - k + 1),
                    )[p]
                )
                ry.append([int(n - k) if p == len(cur) else 0, 0, 0])
                rw.append(len(cur) + 1)
            x = torch.stack(rx)
            w = torch.tensor(rw)
            mu = F.softplus(rates(x))
            y = torch.tensor(ry)
            mask = torch.cat(
                (torch.ones_like(x[:, :1]), x[:, -5, None].expand(-1, 2)), 1
            )
            rl = (
                ((mu - y * mu.clamp_min(1e-8).log()) * mask).sum(1) * w
            ).sum() / w.sum()
            logits = marks.choice(torch.stack(ax)).flatten()
            w = torch.tensor(aw)
            ml = (
                F.binary_cross_entropy_with_logits(
                    logits, torch.tensor(ay).float(), reduction="none"
                )
                * w
            ).sum() / w.sum()
            loss = 0.75 * (ml + rl)
            for kind, net in (("mark", marks.choice), ("rate", rates)):
                data = legacy[kind]
                ii = rng.integers(len(data[0]), size=32)
                loss += 0.25 * objective(net, [v[ii] for v in data], kind)[0]
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(opt.param_groups[0]["params"], 5.0)
            opt.step()
            total += len(rows)
        losslog.append(float(loss.detach()))
    torch.save([marks.state_dict(), rates.state_dict()], directory / "weights.pt")
    if joint:
        ck = torch.load(a.actor, weights_only=True)
        ck["parameters"] = actor.state_dict()
        torch.save(ck, directory / "actor.pt")
        torch.save(scorer.state_dict(), directory / "scorer.pt")
    (directory / "fit.json").write_text(
        json.dumps(
            {
                "seed": seed,
                "arm": arm,
                "visits": total,
                "epochs": a.epochs,
                "last_batch_loss": losslog,
            }
        )
    )
    print("fit", arm, seed, total, flush=True)


def main(a):
    torch.set_num_threads(1)
    groups, sources = contexts(a) if a.action == "fit" else ({}, [])
    jobs = [(arm, seed) for arm in a.arms for seed in a.seeds]
    for arm, seed in jobs:
        if a.action == "fit":
            train(a, groups, sources, arm, seed)
    if a.action != "run":
        return
    from types import SimpleNamespace

    for b in range(2):
        rows = [(arm, seed, case) for case in CASES for arm, seed in jobs]
        for arm, seed, case in rows if not b else reversed(rows):
            root = a.out / "fine" / f"s{seed}"
            d = root / (arm + "-n10000")
            kw = SimpleNamespace(
                out=root,
                actor=d / "actor.pt" if arm == "joint" else a.actor,
                scorer_path=d / "scorer.pt" if arm == "joint" else None,
                data=a.data,
                device_gnn=False,
                timing_prefix="cpu-",
                seconds=480,
                model_sizes=(
                    "1M" if arm == "wide_mark" else "100K",
                    "1M" if arm == "wide_rate" else "100K",
                ),
            )
            execute_one(kw, arm, "n10000", "cpu", case, b)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["fit", "run"])
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--previous", type=Path, required=True)
    p.add_argument("--epochs", type=int, default=2)
    p.add_argument(
        "--arms", nargs="+", default=["frozen", "wide_mark", "wide_rate", "joint"]
    )
    p.add_argument("--seeds", nargs="+", type=int, default=[243, 8201])
    p.add_argument("--data", type=Path, default=Path("/tmp/dfm-local/data"))
    p.add_argument(
        "--actor", type=Path, default=Path("run-recall/higher-scaling/weights/actor.pt")
    )
    main(p.parse_args())
