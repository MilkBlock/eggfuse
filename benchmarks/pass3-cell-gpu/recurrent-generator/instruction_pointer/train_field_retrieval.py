"""Fit role-routed shared field keys with contrastive native request labels."""

import argparse
import json
import random
from pathlib import Path

import torch

from anchor_set_audit import check
from field_retrieval import FieldEncoder
from higher_cell import read
from relation_cases import episodes, request


def train(root, out):
    rng = random.Random(871)
    torch.manual_seed(871)
    examples = []
    for case in ("sum", "dot"):
        folder = root / case
        packets = []
        groups = []

        def collect(run, rid, store, keys, truth, x, y, flip):
            if y is None or not x[1].shape[1]:
                return
            pos = [i for i, k in enumerate(keys) if k in truth]
            if not pos:
                return
            ids = sorted(
                set(pos[:4] + rng.sample(range(len(keys)), min(16, len(keys))))
            )
            start = len(packets)
            for i in ids:
                p = request(run, rid, keys[i], store)
                p["token"] = len(packets) + 1
                packets.append(p)
            groups.append(
                (start, x[1].reshape(-1, 64), y[1][ids].reshape(len(ids), -1, 64))
            )

        episodes(folder, 80, 9417, collect, rename_seed=871)
        labels = check(
            folder,
            root / "whole-fork-credit/receiver",
            read(folder / "tape.json"),
            packets,
        )["recall_verdicts"]
        for start, q, k in groups:
            valid = torch.tensor(
                [w is not None for _, _, w, _ in labels[start : start + len(k)]]
            )
            if valid.any() and not valid.all():
                examples.append((q, k, valid))
    model = FieldEncoder().to("mps")
    opt = torch.optim.AdamW(model.parameters(), lr=0.002)
    # Batch by actual field count and candidate count; each row uses its own memory negatives.
    from collections import defaultdict

    shapes = defaultdict(list)
    for q, k, valid in examples:
        shapes[tuple(k.shape)].append((q, k, valid))
    pools = [
        tuple(torch.stack(x).to("mps") for x in zip(*group))
        for group in shapes.values()
    ]
    for _ in range(400):
        qs, ks, ys = rng.choices(pools, weights=[len(x[0]) for x in pools])[0]
        ids = torch.randint(len(ys), (32,), device="mps")
        scores = (model(qs[ids], True)[:, None] * model(ks[ids])).sum(-1).mean(-1) * 8
        loss = (
            scores.logsumexp(1) - scores.masked_fill(~ys[ids], -torch.inf).logsumexp(1)
        ).mean()
        opt.zero_grad()
        loss.backward()
        opt.step()
    out.mkdir(exist_ok=True, parents=True)
    torch.save(model.cpu().state_dict(), out / "field.pt")
    (out / "training.json").write_text(
        json.dumps(
            dict(
                events=len(examples),
                positive=sum(int(y.sum()) for _, _, y in examples),
                negative=sum(int((~y).sum()) for _, _, y in examples),
                steps=400,
                seed=871,
            )
        )
        + "\n"
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("out", type=Path)
    a = p.parse_args()
    torch.set_num_threads(1)
    train(a.root, a.out)
