"""Train ten prespecified single-row models, supervising only after both Runs."""

import argparse
import json
import os
from pathlib import Path
import time

import numpy as np
import torch

from study import Study, BATCH, STEPS, SEEDS, VALUE_CLASSES, MANIFEST, digest
from learning import ARMS, System, align, objective


def device():
    if (
        not torch.backends.mps.is_available()
        or os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK", "0") != "0"
    ):
        raise RuntimeError("This experiment requires MPS with CPU fallback disabled")
    return torch.device("mps")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("arm", choices=(*ARMS, "wide_roles"))
    p.add_argument("seed", type=int, choices=SEEDS)
    args = p.parse_args()
    dev = device()
    study = Study()
    out = args.root / f"{args.arm}-{args.seed}"
    out.mkdir(parents=True, exist_ok=True)
    if (out / "model.pt").exists():
        raise FileExistsError(out)
    from data import dataset

    training = {t["id"]: dataset("train", t) for t in study.train}
    graphs = {t["id"]: study.schema.pack(t, dev) for t in study.train}
    model = System(
        study.schema, len(study.rules), args.arm, study.columns, VALUE_CLASSES, args.seed
    )
    initial = model.initial_digests()
    num_parameters = sum(p.numel() for p in model.parameters())
    model = model.to(dev)
    opt = torch.optim.Adam(model.parameters(), lr=0.001)
    rng = np.random.default_rng(args.seed)
    order = []
    history = []
    start = time.perf_counter()
    for step in range(STEPS):
        if not order:
            order = list(rng.permutation(len(study.train)))
        t = study.train[order.pop()]
        tid = t["id"]
        d = training[tid]
        ix = rng.integers(len(d["a"]), size=BATCH)
        inputs = [
            torch.as_tensor(d[k][ix], device=dev, dtype=torch.int32) for k in ("a", "b", "requests")
        ]
        opt.zero_grad(set_to_none=True)
        stages, _ = model.infer(inputs, study.static(t), model.encoder(graphs[tid]))
        labels = align(stages, d["target1"][ix], d["target2"][ix])
        if any(v[..., 3:].min() < 0 or v[..., 3:].max() >= VALUE_CLASSES for v in labels):
            raise ValueError("auxiliary value domain")
        val = objective(
            model, stages, [torch.as_tensor(y, device=dev, dtype=torch.long) for y in labels], 0
        )
        val.backward()
        opt.step()
        if step % 384 == 0 or step + 1 == STEPS:
            item = dict(step=step + 1, loss=val.item(), seconds=time.perf_counter() - start)
            history.append(item)
            if not np.isfinite(item["loss"]):
                raise ValueError("nonfinite fit")
            print(item, flush=True)
    torch.save(model.state_dict(), out / "model.pt")
    report = dict(
        arm=args.arm,
        seed=args.seed,
        initial=initial,
        parameters=num_parameters,
        head_parameters=sum(p.numel() for p in model.decoder.heads.parameters()),
        encoder_parameters=sum(p.numel() for p in model.encoder.parameters()),
        manifest_sha256=digest(MANIFEST),
        weight_sha256=digest(out / "model.pt"),
        steps=STEPS,
        batch=BATCH,
        train_ids=sorted(training),
        train_graphs=sum(len(d["a"]) for d in training.values()),
        history=history,
        torch=torch.__version__,
        mode="mps",
    )
    (out / "fit.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
