"""Score a held-out program family with independent bridge draws and balanced weights."""

import argparse
import json
from pathlib import Path

import numpy as np
import torch
from torch.nn import functional as F

from data_scale_train import Bank
from metal_scaling import models
from recursive_train import read


@torch.inference_mode()
def main(a):
    torch.set_num_threads(1)
    corpus = read(a.out / "held/corpus.json")
    train_sigs = {r["signature"] for r in read(a.out / "corpus.json")}
    if train_sigs & {r["signature"] for r in corpus}:
        raise ValueError("held program leakage")
    held = Bank(a.out / "held", corpus)
    rng = np.random.default_rng(8291)
    ids = rng.choice(len(held.width), min(len(held.width), 32768), replace=False)
    rate, mark = held.draw(ids, rng)
    out = []
    for root in [a.out, a.out / "fixed1568"]:
        for path in sorted(root.glob("s*/*/fit.json")):
            info = read(path)
            m, r = models(info["size"])
            for model, sd in zip(
                (m, r),
                torch.load(path.parent / "weights.pt", weights_only=True),
                strict=True,
            ):
                model.load_state_dict(sd)
            results = {}
            for k, net, ds in (("mark", m.choice, mark), ("rate", r, rate)):
                pred = torch.cat([net(x) for x in ds[0].split(1024)])
                x, y, w = ds
                if k == "mark":
                    loss = F.binary_cross_entropy_with_logits(
                        pred.flatten(), y, reduction="none"
                    )
                    results["address_accuracy"] = (
                        (pred.flatten().ge(0) == y.bool()).float().mean().item()
                    )
                    for idx, kind in enumerate(("template", "port", "copy_projection")):
                        mask = x[:, -3 + idx] > 0
                        results[kind + "_accuracy"] = float(
                            (pred.flatten()[mask].ge(0) == y[mask].bool())
                            .float()
                            .mean()
                        )
                else:
                    p = F.softplus(pred)
                    allowed = torch.cat(
                        (torch.ones_like(y[:, :1]), x[:, -5, None].expand(-1, 2)), 1
                    )
                    loss = ((p - y * p.clamp_min(1e-8).log()) * allowed).sum(1)
                results[k + "_loss"] = float((loss * w).sum() / w.sum())
            out.append(
                dict(
                    budget=root.name if root != a.out else "complete",
                    size=info["size"],
                    n=info["n"],
                    seed=info["seed"],
                    rows=len(ids),
                    **results,
                )
            )
    (a.out / "held-metrics.json").write_text(json.dumps(out) + "\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    main(p.parse_args())
