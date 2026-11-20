"""Offline contextual bandit. Actions assign the next source observation batch to 1–8 real Rust rows."""

import argparse
import json
from pathlib import Path

import numpy as np
import torch
from torch import nn


def train(args):
    torch.set_num_threads(1)
    raw = json.loads((args.capture / "reward.json").read_bytes())
    args.out.mkdir(parents=True, exist_ok=False)
    for seed in args.seeds:
        relevant = {k: v for k, v in raw.items() if k.split("/")[2] == str(seed)}
        names = sorted({k.split("/")[0] for k in relevant})
        assert len(names) == 4
        # Each observation keeps its program, multiplicity and measured counterfactual timings.
        x = []
        time = []
        for rows in relevant.values():
            for features, cost in rows:
                x.append(features)
                time.append(cost)
        x = torch.tensor(x, dtype=torch.float32)
        y = torch.tensor(time, dtype=torch.float32)
        # Winsorize timer interruptions. Train on actual latency (ns), not a label for correctness.
        clip = torch.quantile(y, 0.99, dim=0)
        y = torch.minimum(y, clip)
        for limit in (1, 2, 4, 8):
            allowed = torch.tensor([1 << (i % 4) <= limit for i in range(8)])
            for size in args.sizes:
                for method in ("policy-gradient", "supervised"):
                    torch.manual_seed(seed)
                    rng = np.random.default_rng(seed)
                    layers = nn.Sequential(
                        nn.Linear(5, size), nn.Tanh(), nn.Linear(size, 8)
                    )
                    opt = torch.optim.Adam(layers.parameters(), lr=0.012)
                    for step in range(args.updates):
                        ix = torch.from_numpy(rng.integers(len(x), size=128))
                        logits = layers(x[ix]).masked_fill(~allowed, -1e8)
                        cost = y[ix]
                        if method == "policy-gradient":
                            dist = torch.distributions.Categorical(logits=logits)
                            choice = dist.sample()
                            # Only the sampled action's native timing is returned. The incumbent
                            # single memo row supplies an action-independent variance baseline.
                            advantage = (
                                cost[:, 4] - cost.gather(1, choice[:, None])[:, 0]
                            ) / 1e4
                            loss = -(
                                dist.log_prob(choice) * advantage.detach()
                                + 0.001 * dist.entropy()
                            ).mean()
                        else:
                            target = cost.masked_fill(~allowed, 1e20).argmin(1)
                            loss = nn.functional.cross_entropy(logits, target)
                        opt.zero_grad()
                        loss.backward()
                        nn.utils.clip_grad_norm_(layers.parameters(), 1.0)
                        opt.step()
                    with torch.no_grad():
                        chosen = layers(x).masked_fill(~allowed, -1e8).argmax(1)
                        record = {
                            "seed": seed,
                            "method": method,
                            "size": size,
                            "max_rows": limit,
                            "programs": names,
                            "updates": args.updates,
                            "samples": len(x),
                            "params": sum(p.numel() for p in layers.parameters()),
                            "train_choices": chosen.bincount(minlength=8).tolist(),
                            "train_mean_ns": float(y.gather(1, chosen[:, None]).mean()),
                            "train_static_mean_ns": y.mean(0).tolist(),
                            "weights": {
                                "hidden": layers[0].weight.tolist(),
                                "bias": layers[0].bias.tolist(),
                                "decisions": layers[2].weight.tolist(),
                                "offsets": layers[2].bias.tolist(),
                            },
                        }
                    (args.out / f"{seed}-{method}-{size}-{limit}.json").write_text(
                        json.dumps(record, separators=(",", ":")) + "\n"
                    )
        print(seed, names, len(x), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("capture", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--seeds", type=int, nargs="+", default=[1703, 1709])
    p.add_argument("--sizes", type=int, nargs="+", default=[2, 8, 32])
    p.add_argument("--updates", type=int, default=360)
    train(p.parse_args())
