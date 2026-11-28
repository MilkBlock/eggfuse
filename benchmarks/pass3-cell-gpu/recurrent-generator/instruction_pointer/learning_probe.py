"""Entropy, mass and finite-budget discovery on deduplicated held-out native target sets."""

import math
import os
from collections import defaultdict

import numpy as np
import torch

from competition_draw import Page
from exposure_train import output
from learning_entropy import size_group, table
from partner_index_worlds import args
from scaling_archive import directory
from scaling_fit import model
from scaling_pool import Pool, Sampler
from teacher_forcing import complete_nll


def run(a, name):
    origin = directory(a) / "fits/local-s71-t100000.pt"
    weights = (output(a) / (name + ".pt")) if "/" in name else origin
    full = name.startswith("matched-end-to-end")
    n, _ = model(a, {"arm": "C" if full else "A"}, 71)
    n.load_state_dict(torch.load(weights, weights_only=True))
    p = Pool(a, n)
    n.eval()
    known = {}
    measured = defaultdict(int)
    rows = []
    for key, w, s, ts in p.val:
        known.setdefault(key, (w, s, set()))[2].update(ts)
    with torch.no_grad():
        for key, (w, s, targets) in sorted(known.items()):
            ts = sorted(targets)
            k = len(ts)
            g = size_group(k)
            nll = torch.cat(
                [complete_nll(n, [(w, s, ts[i : i + 128])]) for i in range(0, k, 128)]
            ).double()
            prob = (-nll).exp().clamp(max=1)
            ce = float(nll.mean())
            mass = float(prob.sum())
            row = {
                "program": key[0],
                "state": key[1],
                "k": k,
                "group": g,
                "ce": ce,
                "h": math.log(k),
                "excess": ce - math.log(k),
                "known_mass": mass,
            }
            for budget in (16, 64, 256):
                row[f"iid_recall_{budget}"] = float(
                    (-torch.expm1(budget * torch.log1p(-prob))).mean()
                )
            if measured[g] < 12:
                n.prepare(w)
                n.physical = ("held", 0)
                samples = [
                    Page(n, w, s).draws(np.random.default_rng(seed), 256, True)
                    for seed in (193, 307)
                ]
                for budget in (16, 64, 256):
                    row[f"actual_recall_{budget}"] = sum(
                        len(set(x[:budget]) & targets) for x in samples
                    ) / (2 * k)
                measured[g] += 1
            rows.append(row)
    tag = name.replace("/", "_")
    table("sets-" + tag + ".csv", rows)
    # A common offline training probe isolates nonzero gradients from cumulative movement.
    n.train()
    n.zero_grad(set_to_none=True)
    sampler = Sampler(p, 71, {})
    for _ in range(32):
        _, w, s, ts = sampler.next(1)
        (complete_nll(n, [(w, s, ts)]).mean() / 32).backward()
    start = torch.load(origin, weights_only=True)
    grad = []
    for key, t in n.named_parameters():
        delta = (t.detach() - start[key]).double()
        z = t.grad
        grad.append(
            {
                "parameter": key,
                "module": key.rsplit(".", 1)[0],
                "count": t.numel(),
                "trainable": t.requires_grad,
                "gradient_connected": z is not None,
                "nonzero_grad": int(z.count_nonzero()) if z is not None else 0,
                "grad_norm": float(z.double().norm()) if z is not None else 0.0,
                "start_norm": float(start[key].double().norm()),
                "delta_norm": float(delta.norm()),
                "changed": int(delta.count_nonzero()),
            }
        )
    table("parameters-" + tag + ".csv", grad)


if __name__ == "__main__":
    torch.set_num_threads(1)
    run(args(), os.environ["EXPOSURE_MODELS"])
