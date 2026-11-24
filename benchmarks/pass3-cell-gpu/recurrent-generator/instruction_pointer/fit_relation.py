"""Train the shared composition scorer on native-labeled sum and dot proposals."""

from pathlib import Path
import argparse
import json
import random

import torch
from torch.nn import functional as F
from anchor_set_audit import check
from composition_relation import Relation
from higher_cell import read
from relation_cases import episodes, request


def fit(root, binary, out):
    rng = random.Random(9417)
    torch.manual_seed(9417)
    examples = [[], []]
    signature = set()
    producers = set()
    for case in ("sum", "dot"):
        folder = root / case
        packets = []
        features = []
        sigs = []

        def collect(run, rid, store, keys, truth, x, y, flip):
            positive = [i for i, k in enumerate(keys) if k in truth]
            if not positive and rng.random() > 0.05:
                return
            sampled = set(positive + rng.sample(range(len(keys)), min(4, len(keys))))
            for j in sorted(sampled):
                q = request(run, rid, keys[j], store)
                q["token"] = len(packets) + 1
                packets.append(q)
                a = x[0][0]
                b = y[0][j] if y else torch.zeros_like(a)
                width = max(1, x[1].shape[1])
                left = x[1][0] / width**0.5
                right = y[1][j] / width**0.5 if y else left
                features.append((b if flip else a, a if flip else b, left, right))
                sig = store.iface.key(rid, keys[j], store.types)
                sigs.append((bool(y), sig))

        episodes(folder, 80, 9417, collect, rename_seed=9417)
        audit = check(folder, binary, read(folder / "tape.json"), packets)
        for _, token, w, _ in audit["recall_verdicts"]:
            binary_case, sig = sigs[token - 1]
            a, b, left, right = features[token - 1]
            examples[int(binary_case)].append((a, b, left, right, int(w is not None)))
            signature.add(json.dumps(sig))
            producers.update(x[2] for x in sig[1])
    device = "mps"
    model = Relation().to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=0.003)
    sets = []
    for rows in examples:
        a, b, left, right, y = zip(*rows)
        pad = lambda seq: torch.nn.utils.rnn.pad_sequence(seq, batch_first=True).to(
            device
        )
        sets.append(
            (
                torch.stack(a).to(device),
                torch.stack(b).to(device),
                pad(left),
                pad(right),
                torch.tensor(y, device=device, dtype=torch.float32),
            )
        )
    for step in range(900):
        ab = step % 2
        a, b, left, right, y = sets[ab]
        idx = torch.randint(len(y), (256,), device=device)
        h = model.encoder(a[idx])
        logits = (
            (model.q(h) * model.k(model.encoder(b[idx]))).sum(-1)
            + F.softplus(model.scale).square() * (left[idx] * right[idx]).sum(-1)
            if ab
            else model.unary(h).flatten()
        )
        loss = F.binary_cross_entropy_with_logits(logits, y[idx])
        opt.zero_grad()
        loss.backward()
        opt.step()
    out.mkdir(parents=True, exist_ok=True)
    torch.save(model.cpu().state_dict(), out / "model.pt")
    (out / "train.json").write_text(
        json.dumps(
            dict(
                signatures=sorted(signature),
                producers=sorted(producers),
                examples=[[len(rows), sum(z[-1] for z in rows)] for rows in examples],
                steps=900,
                seed=9417,
            )
        )
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for k in ("root", "binary", "out"):
        p.add_argument(k, type=Path)
    args = p.parse_args()
    torch.set_num_threads(1)
    fit(args.root, args.binary, args.out)
