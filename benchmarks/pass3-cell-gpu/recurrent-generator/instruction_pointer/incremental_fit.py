"""Matched complete-Cell CE exposures; measure actual gradient reach at every step."""

import json
import os
import random
from pathlib import Path
from time import perf_counter

import torch

from int_parameters import digest
from joint_cell_sweep import complete_ce
from joint_cell_train import build, fitted, legacy_examples
from partner_index_worlds import args


def output(a):
    d = a.out / "incremental-foundation"
    d.mkdir(exist_ok=True)
    return d


def corpus(a, case, model):
    groups = build(a, case, model)
    groups["legacy"] = legacy_examples(a, model)
    data = {}
    counts = {}
    for src, rs in groups.items():
        lookup = {}
        for w, s, targets in rs:
            key = str(w.dir), digest(s)
            lookup.setdefault(key, (w, s, set()))[2].update(targets)
        keys = list(lookup)
        random.Random(193).shuffle(keys)
        chosen = keys[:32]
        counts[src] = len(chosen)
        for k in chosen:
            w, s, t = lookup[k]
            data.setdefault(k, (w, s, set()))[2].update(t)
    manifest = [(Path(k[0]).name, k[1], sorted(t)) for k, (_, _, t) in data.items()]
    return [(w, s, sorted(t)) for w, s, t in data.values()], counts, digest(manifest)


def train(a, case):
    out = output(a)
    data, sources, signature = corpus(a, case, fitted(a, case, "sweep", 0))
    for seed in map(int, os.getenv("IK_SEEDS", "71 113").split()):
        for arm in os.getenv("IK_ARMS", "C B A").split():
            stem = f"{case}-{arm}-{seed}"
            if (out / (stem + ".json")).exists():
                continue
            n = fitted(a, case, "sweep", 0)
            n.train()
            n.grouped_training_reduction = True
            n.train_graph = arm == "C"
            if arm != "A":
                for k in ("lanes", "next_read"):
                    getattr(n.actor, k).requires_grad_(True)
            if arm == "C":
                n.requires_grad_(True)
            initial = {k: p.detach().clone() for k, p in n.named_parameters()}
            opt = torch.optim.AdamW(
                [p for p in n.parameters() if p.requires_grad], lr=0.001, weight_decay=0
            )
            rng = random.Random(seed)
            indices = list(range(len(data)))
            curve = []
            gradients = {}
            connected = set()
            seen = steps = 0
            start = perf_counter()
            for epoch in range(3):
                rng.shuffle(indices)
                weighted = exposure = 0
                for idx in indices:
                    w, s, targets = data[idx]
                    n.prepare(w)
                    n.physical = ("held", 0)
                    m = n.state(w, s)
                    ce = complete_ce(n, w, m, targets)
                    opt.zero_grad(set_to_none=True)
                    ce.backward()
                    for k, p in n.named_parameters():
                        if p.grad is not None:
                            connected.add(k)
                            mask = p.grad.detach() != 0
                            if k not in gradients:
                                gradients[k] = mask.clone()
                            else:
                                gradients[k] |= mask
                    torch.nn.utils.clip_grad_norm_(
                        n.parameters(), 2.0, error_if_nonfinite=True
                    )
                    opt.step()
                    steps += 1
                    exposure += len(targets)
                    weighted += float(ce.detach()) * len(targets)
                seen += exposure
                seconds = perf_counter() - start
                curve.append(
                    {
                        "epoch": epoch + 1,
                        "steps": steps,
                        "exposures": seen,
                        "ce": weighted / exposure,
                        "seconds": seconds,
                        "token_per_s": seen / seconds,
                    }
                )
                path = out / f"{stem}-e{epoch + 1}.pt"
                temporary = path.with_suffix(".pt.tmp")
                torch.save(n.state_dict(), temporary)
                temporary.replace(path)
                print(stem, curve[-1], flush=True)
            params = dict(n.named_parameters())
            metrics = {
                k: {
                    "numel": p.numel(),
                    "connected": k in connected,
                    "nonzero": int(gradients[k].sum()) if k in gradients else 0,
                    "changed": int((p.detach() != initial[k]).sum()),
                }
                for k, p in params.items()
            }
            (out / (stem + ".json")).write_text(
                json.dumps(
                    {
                        "case": case,
                        "arm": arm,
                        "seed": seed,
                        "curve": curve,
                        "sources": sources,
                        "signature": signature,
                        "states": len(data),
                        "targets": sum(len(t) for _, _, t in data),
                        "registered": sum(p.numel() for p in params.values()),
                        "enabled": sum(
                            p.numel() for p in params.values() if p.requires_grad
                        ),
                        "params": metrics,
                    }
                )
            )


if __name__ == "__main__":
    torch.set_num_threads(1)
    train(args(), os.environ["TR_CASE"])
