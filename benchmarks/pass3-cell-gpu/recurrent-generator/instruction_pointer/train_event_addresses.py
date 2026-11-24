"""Backward-label address instructions from committed Cell proofs on training programs."""

import argparse, json
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np
import torch
from torch.nn import functional as F
from event_addresses import AddressNet, Directory
from protocol_experiment import dump
from recursive_agent import Reader
from recursive_train import read, folder, keys


def examples(root, d, seed):
    rd = Reader(read(d / "program.json"), root, rename_seed=seed)
    cost = Counter()
    directory = Directory(rd, cost)
    teacher = defaultdict(list)
    for q in read(d / "tape.json")["requests"]:
        teacher[q["run"]].append(q)
    xs, ys = [], []
    rng = np.random.default_rng(seed)

    def append(x, ys0, lo=None, hi=None):
        xs.append(x)
        y = np.full((len(x), 3), -1.0, np.float32)
        y[:, 0] = ys0
        if lo is not None:
            y[:, 1], y[:, 2] = lo, hi
        ys.append(y)

    for frame in map(json.loads, (d / "memory.jsonl").open()):
        rd.advance(frame)
        rules = dict(frame["rules"])
        by = defaultdict(list)
        for q in teacher[frame["run"]]:
            r = q["rule"]
            parents = []
            for j, (token, op) in enumerate(keys(q)):
                bank = directory.bank(directory.roles[r][j])
                pos = bank.positions.get((rd.store.alias(token), op))
                if pos is None:
                    break
                parents.append(pos)
            if len(parents) != len(q["parents"]):
                continue
            if not parents:
                by[r, -1].append(())
            for j, pos in enumerate(parents):
                if directory.bank(directory.roles[r][j]).rows[pos, 2] >= rules[r]:
                    by[r, j].append(tuple(parents))
        for r, j, ix in directory.events(rules):
            order = directory.order(r, j)
            group = by[r, j]
            good = {p[j] if order else 0 for p in group}
            neg = np.array([i for i in ix if i not in good], dtype=int)
            chosen = np.array(
                sorted(good)
                + rng.choice(
                    neg, min(3 + len(good) * 2, len(neg)), replace=False
                ).tolist(),
                dtype=int,
            )
            if not len(chosen):
                continue
            paths = chosen[:, None] if order else np.empty((len(chosen), 0), dtype=int)
            append(
                directory.features(r, order[:1], paths, 0), np.isin(chosen, list(good))
            )
            for depth, dest in enumerate(order[1:], 1):
                packed = defaultdict(set)
                for p in group:
                    packed[tuple(p[a] for a in order[:depth])].add(p[dest])
                if not packed:
                    continue
                paths = np.array(list(packed))
                post, start, n = directory.window(r, order[:depth], dest, paths)
                x = directory.features(r, order[:depth], paths, n)
                for k, (key, targets) in enumerate(packed.items()):
                    lanes = (
                        range(start[k], start[k] + n[k])
                        if post is None
                        else post[start[k] : start[k] + n[k]]
                    )
                    gold = [a for a, i in enumerate(lanes) if i in targets]
                    if not gold:
                        cost["out_of_address_domain"] += 1
                        continue
                    scale = max(int(n[k]) - 1, 1)
                    append(x[k : k + 1], 1, min(gold) / scale, max(gold) / scale)
                    cost["named_partner_labels"] += len(gold)
    return np.concatenate(xs), np.concatenate(ys), cost


def fit(root, out, donor):
    parts = []
    counts = {}
    for i, d in enumerate(
        [
            donor,
            folder(root, "loopfact"),
            folder(root, "grammar-17118"),
            folder(root, "grammar-17119"),
        ]
    ):
        x, y, c = examples(root, d, 9031 + i)
        counts[d.name] = dict(c, samples=len(y))
        parts.append((x, y))
    torch.manual_seed(4371)
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    x, y = [torch.from_numpy(np.concatenate(v)).to(dev) for v in zip(*parts)]
    net = AddressNet().to(dev)
    opt = torch.optim.AdamW(net.parameters(), lr=0.003)
    good = torch.where(y[:, 0] > 0)[0]
    for _ in range(800):
        ix = torch.cat(
            [
                torch.randint(len(x), (192,), device=dev),
                good[torch.randint(len(good), (64,), device=dev)],
            ]
        )
        pred = net(x[ix])
        target = y[ix]
        has = target[:, 1] >= 0
        loss = F.binary_cross_entropy_with_logits(pred[:, 0], target[:, 0])
        bounds = F.smooth_l1_loss(
            pred[:, 1:].sigmoid(), target[:, 1:], reduction="none"
        )
        loss = loss + 4 * (bounds.mean(1) * has).sum() / has.sum().clamp_min(1)
        opt.zero_grad()
        loss.backward()
        opt.step()
    torch.save(net.cpu().state_dict(), out / "events.pt")
    dump(
        out / "events-fit.json", dict(programs=counts, steps=800, device=dev, seed=4371)
    )
    print(counts, flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for arg in ("root", "out", "donor"):
        p.add_argument(arg, type=Path)
    a = p.parse_args()
    torch.set_num_threads(1)
    fit(a.root, a.out, a.donor)
