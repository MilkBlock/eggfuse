"""Nested native plan corpora; sample the ordered edit bridge and conditional address labels."""

import argparse
import json
from pathlib import Path
from time import perf_counter

import numpy as np
import torch
from torch.nn import functional as F

from metal_scaling import assess, models, objective
from recursive_train import read

LEVELS = (10_000, 100_000, 1_000_000)
SEEDS = (243, 8201, 536)


def subset_indices(sizes, total, n):
    # Round-robin over increasingly many entire program families. All smaller pools are nested.
    count = min({10000: 16, 100000: 64, 1000000: len(sizes)}[n], len(sizes))
    ordered = np.lexsort(
        (
            np.repeat(np.arange(count), sizes[:count]),
            np.concatenate([np.arange(s) for s in sizes[:count]]),
        )
    )
    if len(ordered) < n:
        raise ValueError("insufficient distinct target plans")
    result = ordered[:n]
    if n > 10000:
        prev = subset_indices(sizes, total, 10000 if n == 100000 else 100000)
        selected = np.zeros(total, dtype=bool)
        selected[prev] = True
        result = np.r_[prev, ordered[~selected[ordered]][: n - len(prev)]]
    assert len(np.unique(result)) == n
    return result


class Bank:
    def __init__(self, root, meta):
        blocks = {
            k: [] for k in ("mark", "label", "state", "event", "offsets", "vector")
        }
        rows = []
        marks = requests = frames = 0
        for d in meta:
            path = root / "programs" / f"{d['id']:04d}"
            f = torch.load(path / "features.pt", weights_only=True)
            plan = np.load(path / "plans.npy")
            run_map = {v: i + frames for i, v in enumerate(f["runs"])}
            plan[:, 0] = np.array([run_map[int(n)] for n in plan[:, 0]])
            plan[:, 1:] += np.where(plan[:, 1:] >= 0, requests, 0)
            f["offsets"][:, 0] += marks
            for k, parts in blocks.items():
                parts.append(f[k])
            rows.append(plan)
            marks += len(f["mark"])
            requests += len(f["vector"])
            frames += len(f["state"])
        for k, arr in blocks.items():
            setattr(self, k, torch.cat(arr))
        self.plans = torch.from_numpy(np.concatenate(rows)).long()
        self.shard_sizes = np.array(list(map(len, rows)))
        self.width = (self.plans[:, 1:] >= 0).sum(1).numpy()

    def draw(self, ids, rng):
        p = self.plans[ids]
        width = self.width[ids]
        b = len(ids)
        # Empty or a valid unissued prefix. Remaining insertions have the same mark input
        # across prefixes because source and destination tables of a stage are disjoint.
        start = (rng.random(b) * width).astype(int) * (rng.random(b) < 0.5)
        n = width - start
        k = (rng.random(b) * (n + 1)).astype(int)
        t = rng.beta(k + 1, n - k + 1)
        length = start + k
        pos = (rng.random(b) * (length + 1)).astype(int)
        ix = np.arange(b)

        def at(index, mask):
            ref = p[ix, np.clip(index, 0, 3) + 1]
            return self.vector[ref.clamp_min(0)] * torch.from_numpy(mask[:, None])

        cur = at(pos, pos < length)
        left = at(pos - 1, pos > 0)
        right = at(pos + 1, pos + 1 < length)
        scalars = np.array(
            [
                t,
                pos < length,
                pos > 0,
                pos + 1 < length,
                np.log1p(length),
                pos / np.maximum(1, length),
            ]
        ).T
        rate_x = torch.cat(
            (
                self.state[p[:, 0]],
                self.event[p[:, 0]],
                cur,
                (cur - left).abs(),
                (cur - right).abs(),
                torch.from_numpy(scalars).float(),
            ),
            1,
        )
        rate_y = torch.zeros(b, 3)
        rate_y[:, 0] = torch.from_numpy((n - k) * (pos == length))
        step = (rng.random(b) * n).astype(int)
        request = p[ix, start + step + 1]
        ranges = self.offsets[request].numpy()
        if np.any(ranges[:, 1] == 0):
            raise ValueError("unhandled deterministic address path")
        branch = ranges[:, 0] + (rng.random(b) * ranges[:, 1]).astype(int)
        mark_weight = ranges[:, 1] * (n - step) / (n + 1) * n
        return (rate_x, rate_y, torch.from_numpy(length + 1).float()), (
            self.mark[branch],
            self.label[branch].float(),
            torch.from_numpy(mark_weight).float(),
        )


def run(a):
    torch.set_num_threads(1)
    legacy, legacy_test = torch.load(a.previous / "large.pt", weights_only=True)
    _, held = torch.load(a.previous / "held.pt", weights_only=True)

    for n in a.levels:
        target_count = {10_000: 16, 100_000: 64}.get(n)
        if target_count is None:
            target_count = len(read(a.out / "corpus.json"))
        dirs = [a.out / "programs" / f"{i:04d}" for i in range(target_count)]
        bank = Bank(a.out, [read(d / "verified.json") for d in dirs])
        ids = subset_indices(bank.shard_sizes, len(bank.plans), n)
        for size in a.sizes:
            for seed in a.seeds:
                dest = (
                    (a.out / f"fixed{a.fixed}" if a.fixed else a.out)
                    / f"s{seed}"
                    / (size + f"-n{n}")
                )
                dest.mkdir(exist_ok=True, parents=True)
                if (dest / "fit.json").exists():
                    continue
                torch.manual_seed(seed)
                marks, rates = models(size)
                marks.to("mps")
                rates.to("mps")
                opt = torch.optim.AdamW(
                    [*marks.parameters(), *rates.parameters()], lr=0.0005
                )
                rng = np.random.default_rng(seed)
                # Four complete shuffled passes even at the largest level.
                batch = 512
                epochs = max(4, int(np.ceil(1536 * batch / n)))
                if a.fixed:
                    epochs = int(np.ceil(a.fixed / np.ceil(n / batch)))
                curve = []
                steps = 0
                started = perf_counter()
                eval_ids = ids[np.random.default_rng(3).choice(n, 4096, replace=False)]
                for epoch in range(epochs):
                    for ids_batch in np.array_split(
                        rng.permutation(ids), int(np.ceil(n / batch))
                    ):
                        rate, mark = bank.draw(ids_batch, rng)
                        losses = []
                        for kind, net, part in (
                            ("mark", marks.choice, mark),
                            ("rate", rates, rate),
                        ):
                            x, y, w = [v.to("mps") for v in part]
                            pred = net(x)
                            if kind == "mark":
                                new = (
                                    F.binary_cross_entropy_with_logits(
                                        pred.flatten(), y, reduction="none"
                                    )
                                    * w
                                ).sum() / w.sum()
                            else:
                                allowed = torch.cat(
                                    (
                                        torch.ones_like(x[:, :1]),
                                        x[:, -5, None].expand(-1, 2),
                                    ),
                                    1,
                                )
                                mu = F.softplus(pred)
                                new = (
                                    ((mu - y * mu.clamp_min(1e-8).log()) * allowed).sum(
                                        1
                                    )
                                    * w
                                ).sum() / w.sum()
                            old = legacy[kind]
                            idx = rng.integers(len(old[0]), size=128)
                            oldloss, _ = objective(
                                net, [v[idx].to("mps") for v in old], kind
                            )
                            losses.append(0.75 * new + 0.25 * oldloss)
                        opt.zero_grad(set_to_none=True)
                        sum(losses).backward()
                        opt.step()
                        steps += 1
                        if a.fixed and steps == a.fixed:
                            break
                    if epoch + 1 in {1, epochs // 2, epochs}:
                        er, em = bank.draw(eval_ids, np.random.default_rng(99))
                        results = {}
                        for kind, net, data in (
                            ("mark", marks.choice, em),
                            ("rate", rates, er[:2]),
                        ):
                            results[kind] = {
                                "train": assess(net, data, kind),
                                "held": assess(net, held[kind], kind),
                                "historical_train": assess(
                                    net, legacy_test[kind], kind
                                ),
                            }
                        curve.append(
                            {"epoch": epoch + 1, "updates": steps, "metrics": results}
                        )
                torch.mps.synchronize()
                torch.save(
                    [marks.cpu().state_dict(), rates.cpu().state_dict()],
                    dest / "weights.pt",
                )
                (dest / "fit.json").write_text(
                    json.dumps(
                        {
                            "n": n,
                            "seed": seed,
                            "size": size,
                            "epochs": epochs,
                            "steps": steps,
                            "seconds": perf_counter() - started,
                            "curve": curve,
                        }
                    )
                    + "\n"
                )
                print(n, size, seed, steps, flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--previous", type=Path, required=True)
    p.add_argument("--sizes", nargs="+", default=["100K", "1M"])
    p.add_argument(
        "--fixed",
        type=int,
        default=0,
        help="Use exactly this many optimizer updates at every data level.",
    )
    p.add_argument("--levels", nargs="+", type=int, choices=LEVELS, default=LEVELS)
    p.add_argument("--seeds", nargs="+", type=int, default=SEEDS)
    run(p.parse_args())
