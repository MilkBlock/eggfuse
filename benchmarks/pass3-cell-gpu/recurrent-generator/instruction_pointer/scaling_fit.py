"""Matched complete-token budgets. Each milestone is a durable inference checkpoint."""

import gzip
import itertools
import json
import math
import os
import pickle
from collections import Counter, defaultdict
from time import perf_counter, time

import torch

from joint_cell_sweep import complete_ce
from joint_cell_train import fitted
from partner_index_worlds import args
from scaling_archive import directory
from scaling_pool import Pool, Sampler


def atomic(path, obj):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, sort_keys=True))
    tmp.replace(path)


def save_seen(d, stem, seen):
    dest = d / (stem + ".seen.gz")
    tmp = d / (stem + ".seen.tmp")
    with gzip.open(tmp, "wb", compresslevel=3) as f:
        pickle.dump(dict(seen), f, protocol=5)
    tmp.replace(dest)


def model(a, cfg, seed):
    n = fitted(a, "sum-divisors", "sweep", 0)
    if cfg.get("random_init"):
        torch.manual_seed(seed)
        for child in n.modules():
            reset = getattr(child, "reset_parameters", None)
            if reset is not None:
                reset()
    n.train()
    n.grouped_training_reduction = True
    arm = cfg.get("arm", "C")
    n.train_graph = arm in ("C", "D")
    if arm != "A":
        n.actor.lanes.requires_grad_(True)
        n.actor.next_read.requires_grad_(True)
    fast = {k for k, p in n.named_parameters() if p.requires_grad}
    if n.train_graph:
        n.requires_grad_(True)
    groups = defaultdict(list)
    for k, p in n.named_parameters():
        if p.requires_grad:
            groups[
                cfg.get("encoder_lr", 1.0) if arm == "D" and k not in fast else 1.0
            ].append(p)
    optimizer = getattr(torch.optim, cfg.get("optimizer", "AdamW"))
    opt = optimizer(
        [{"params": v, "multiplier": k} for k, v in groups.items()],
        lr=cfg.get("lr", 0.001),
        weight_decay=cfg.get("wd", 0.0),
        betas=tuple(cfg.get("betas", (0.9, 0.999))),
    )
    return n, opt


def factor(kind, x):
    if kind == "constant":
        return 1.0
    if kind == "linear":
        return 1.0 - x
    if kind == "warmcos":
        if x < 0.05:
            return max(0.05, x / 0.05)
        x = (x - 0.05) / 0.95
    return (1 + math.cos(math.pi * x)) / 2


def train(a, cfg, seed, milestones):
    n, opt = model(a, cfg, seed)
    data = Pool(a, n, cfg.get("extra_egg", False))
    sampler = Sampler(data, seed, cfg)
    dst = directory(a) / "fits"
    dst.mkdir(exist_ok=True)
    base = cfg["name"] + f"-s{seed}"
    seen = defaultdict(set)
    effects = set()
    connected = set()
    counts = Counter()
    emitted = step = 0
    elapsed = weighted = 0.0
    curve = []
    resume = dst / (base + "-resume.pt")
    if resume.exists():
        saved = torch.load(resume, weights_only=False)
        if saved["config"] != cfg or saved["bank"] != data.catalogue_digest:
            raise ValueError("incompatible resumption")
        curve = saved.get("curve", [])
        n.load_state_dict(saved["model"])
        opt.load_state_dict(saved["opt"])
        seen, effects, connected, counts, emitted, step, elapsed, weighted = saved[
            "progress"
        ]
        sampler.rng.setstate(saved["rng"])
        if "domain_rng" in saved:
            sampler.domain_rng.setstate(saved["domain_rng"])
        sampler.retention = saved.get("retention", 0.25)
    forward = set(connected)
    handles = []
    for name, module in n.named_modules():
        names = tuple(f"{name}.{k}" for k, _ in module.named_parameters(recurse=False))
        if names:
            handles.append(
                module.register_forward_pre_hook(
                    lambda mod, args, ks=names: forward.update(ks)
                )
            )
    # CellKV.state indexes the active lane parameter directly before the first GRU.
    forward.add("actor.lanes.weight")
    calibration = []
    start = perf_counter()
    batch = cfg.get("batch", 1)
    horizon = cfg.get("horizon", 10000)
    half_pending = None
    for cap in milestones:
        alias = dst / f"{base}-t{cap}.json"
        if cap < emitted or (cap == emitted and alias.exists()):
            continue
        while emitted < cap:
            if cfg.get("curriculum") == "adaptive" and emitted // 2500 > len(
                calibration
            ):
                import numpy as np

                from competition_draw import Page

                n.eval()
                hits = slots = 0
                with torch.no_grad():
                    for k, w, s, ts in data.val:
                        if not w.dir.name.startswith("foundation-"):
                            continue
                        n.prepare(w)
                        draws = Page(n, w, s).draws(
                            np.random.default_rng(417), 16, False
                        )
                        hits += sum(t in ts for t in draws)
                        slots += 16
                        if slots == 256:
                            break
                calibration.append(hits / max(slots, 1))
                sampler.retention = 0.45 if calibration[-1] < 0.35 else 0.15
                n.train()
            if time() >= float(os.getenv("CELL_STOP_AT", "inf")):
                break
            examples = []
            remaining = cap - emitted
            for _ in range(max(1, int(batch))):
                if not remaining:
                    break
                if half_pending is not None:
                    key, w, s, targets = half_pending
                    half_pending = None
                else:
                    key, w, s, targets = sampler.next(min(1, emitted / horizon))
                    if batch == 0.5:
                        available = targets[:remaining]
                        split = (len(available) + 1) // 2
                        if len(available) > split:
                            half_pending = (key, w, s, available[split:])
                        targets = available[:split]
                ts = targets[:remaining]
                examples.append((key, w, s, ts))
                remaining -= len(ts)
            count = sum(len(x[3]) for x in examples)
            opt.zero_grad(set_to_none=True)
            for key, w, s, ts in examples:
                n.prepare(w)
                n.physical = ("held", 0)
                loss = complete_ce(n, w, n.state(w, s), ts)
                (loss * (len(ts) / count)).backward()
                weighted += float(loss.detach()) * len(ts)
                seen[key].update(ts)
                for t in ts:
                    if t in data.effects.get(key, {}):
                        effects.add((key, data.effects[key][t]))
                counts[data.records[key]] += len(ts)
            for k, p in n.named_parameters():
                if p.grad is not None:
                    connected.add(k)
            clip = cfg.get("clip", 2.0)
            if clip:
                torch.nn.utils.clip_grad_norm_(
                    n.parameters(), clip, error_if_nonfinite=True
                )
            elif not math.isfinite(float(loss.detach())):
                raise ValueError("nonfinite CE")
            boundaries = (0, 10000, 30000, 100000, 250000, 500000, 1000000)
            left, right = next(
                (a, b) for a, b in itertools.pairwise(boundaries) if a <= emitted < b
            )
            for group in opt.param_groups:
                group["lr"] = (
                    cfg.get("lr", 0.001)
                    * group["multiplier"]
                    * factor(
                        cfg.get("schedule", "constant"),
                        (emitted - left) / (right - left),
                    )
                )
            opt.step()
            emitted += count
            step += 1
            if emitted // 1000 != (emitted - count) // 1000 or emitted == cap:
                curve.append(
                    {
                        "exposures": emitted,
                        "steps": step,
                        "cumulative_train_ce": weighted / emitted,
                        "lr": opt.param_groups[-1]["lr"],
                        "seconds": elapsed + perf_counter() - start,
                    }
                )
        wall = elapsed + perf_counter() - start
        progress = (seen, effects, connected, counts, emitted, step, wall, weighted)
        tmp = resume.with_suffix(".tmp")
        torch.save(
            {
                "config": cfg,
                "bank": data.catalogue_digest,
                "model": n.state_dict(),
                "opt": opt.state_dict(),
                "progress": progress,
                "rng": sampler.rng.getstate(),
                "domain_rng": sampler.domain_rng.getstate(),
                "curve": curve,
                "retention": sampler.retention,
            },
            tmp,
        )
        tmp.replace(resume)
        stem = f"{base}-t{emitted}"
        save_seen(dst, stem, seen)
        tmp = dst / (stem + ".weights.tmp")
        torch.save(n.state_dict(), tmp)
        tmp.replace(dst / (stem + ".pt"))
        atomic(
            dst / (stem + ".json"),
            {
                "config": cfg,
                "seed": seed,
                "exposures": emitted,
                "steps": step,
                "states": len(seen),
                "targets": sum(map(len, seen.values())),
                "verified_distinct_effects": len(effects),
                "effect_identity_scope": "only exact native counterfactual gain sets",
                "sources": counts,
                "seconds": wall,
                "tokens_per_s": emitted / wall,
                "train_ce": weighted / max(1, emitted),
                "calibration": calibration,
                "learning_curve": curve,
                "forward_observed": sum(
                    p.numel() for k, p in n.named_parameters() if k in forward
                ),
                "registered": sum(p.numel() for p in n.parameters()),
                "connected": sum(
                    p.numel() for k, p in n.named_parameters() if k in connected
                ),
                "gradient_tensors": sorted(connected),
                "state_pool": len(sampler.keys),
                "archive_sha": data.catalogue_digest,
            },
        )
        print(base, emitted, round(wall, 2), flush=True)
        if emitted < cap:
            break


if __name__ == "__main__":
    torch.set_num_threads(1)
    train(
        args(),
        json.loads(os.environ["CELL_CFG"]),
        int(os.getenv("CELL_SEED", "71")),
        list(map(int, os.getenv("CELL_MILESTONES", "10000").split())),
    )
