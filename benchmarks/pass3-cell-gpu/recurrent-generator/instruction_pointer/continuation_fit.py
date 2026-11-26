"""Fit existing mark and rate weights to executed Run prefixes, with matched optimizer budgets."""

import json

import numpy as np
import torch
from torch.nn import functional as F

from continuation_audit import arguments
from continuation_data import sources
from metal_scaling import models


def poisson(mu_logits, y):
    mu = F.softplus(mu_logits)
    logmu = torch.where(mu_logits < -20, mu_logits, mu.clamp_min(1e-30).log())
    return mu - y * logmu


def fit(a):
    raw = [
        torch.load(a.out / f"corpus-{case}-{src}.pt", weights_only=True)
        for case, src, *_ in sources(a)
    ]
    full = []
    if any(arm.endswith("-full") for arm in a.arms):
        full = [
            torch.load(a.out / f"full-{case}-{src}.pt", weights_only=True)
            for case, src, *_ in sources(a)
        ]
        full.append(torch.load(a.out / "full-sum-rejected.pt", weights_only=True))
    for seed in a.seeds:
        base = a.previous / f"s{seed}/1M-n1000000/weights.pt"
        original = torch.load(base, weights_only=True)
        for arm in a.arms:
            mode = "flow" if arm == "uncensored" else arm.removesuffix("-response")
            corpora = (
                raw
                if not arm.endswith("-response")
                else raw
                + [torch.load(a.out / "corpus-sum-rejected.pt", weights_only=True)]
            )
            if arm.endswith("-full"):
                mode = arm.removesuffix("-full")
                corpora = full
            rng = np.random.default_rng(seed)
            torch.manual_seed(seed)
            marks, rate = models("1M")
            marks.load_state_dict(original[0])
            rate.load_state_dict(original[1])
            marks.to("mps")
            rate.to("mps")
            opt = torch.optim.AdamW(
                [*marks.parameters(), *rate.parameters()], lr=0.00018
            )
            log = []
            for step in range(a.steps):
                idx = int(rng.integers(len(corpora)))
                # Identical mark samples across both arms; draw rate samples from a separate stream.
                mx, my = corpora[idx]["marks"]
                mi = rng.integers(len(mx), size=256)
                x, y, mask = corpora[idx][mode]
                rr = np.random.default_rng(seed + 100003 * step)
                ix = rr.integers(len(x), size=256)
                X, Y, M = (v[ix].to("mps") for v in (x, y, mask))
                if arm == "uncensored":
                    M = torch.ones_like(M)
                rawout = rate(X)
                if mode == "editor":
                    insert = poisson(rawout[:, 0], Y[:, 0]).mean()
                    valid = X[:, -5]
                    cls = (Y[:, 1] + 2 * Y[:, 2]).long()
                    action = F.cross_entropy(
                        torch.cat((torch.zeros_like(rawout[:, :1]), rawout[:, 1:]), 1),
                        cls,
                        reduction="none",
                    )
                    el = insert + (action * valid).mean()
                else:
                    M[:, 1:] *= X[:, -5, None]
                    el = (poisson(rawout, Y) * M).sum(1).mean()
                ml = F.binary_cross_entropy_with_logits(
                    marks.choice(mx[mi].to("mps")).flatten(), my[mi].to("mps")
                )
                opt.zero_grad(set_to_none=True)
                (el + ml).backward()
                opt.step()
                if step in (0, 127, 511, a.steps - 1):
                    log.append([step + 1, float(el.detach()), float(ml.detach())])
            d = a.out / f"s{seed}" / arm
            d.mkdir(parents=True, exist_ok=True)
            torch.save(
                [marks.cpu().state_dict(), rate.cpu().state_dict()], d / "weights.pt"
            )
            (d / "fit.json").write_text(json.dumps(log) + "\n")
            print(seed, arm, log[-1], flush=True)


if __name__ == "__main__":
    p = arguments()
    p.add_argument(
        "--arms",
        nargs="+",
        choices=[
            "editor",
            "flow",
            "uncensored",
            "editor-response",
            "flow-response",
            "editor-full",
            "flow-full",
        ],
        default=["editor", "flow"],
    )
    p.add_argument("--steps", type=int, default=1536)
    p.add_argument("--seeds", nargs="+", type=int, default=[243, 536, 8201])
    torch.set_num_threads(1)
    fit(p.parse_args())
