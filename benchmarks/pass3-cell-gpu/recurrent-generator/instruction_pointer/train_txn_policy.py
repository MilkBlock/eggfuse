"""Fit neural read plans and response-address bits using native training proofs."""

import argparse
import json
from collections import defaultdict
from pathlib import Path

import torch
from torch.nn import functional as F

from recursive_agent import Reader
from recursive_train import folder, keys, read
from txn_policy import TransactionNet, plans, route_features

TRAIN = [f"grammar-{seed}" for seed in range(17118, 17122)]
VALID = "grammar-17122"


def examples(root, case, seed, chains=False):
    d = folder(root, case)
    rd = Reader(read(d / "program.json"), root, rename_seed=seed)
    by = defaultdict(list)
    for r in read(d / "tape.json")["requests"]:
        by[r["run"]].append(r)
    examples = []
    for frame in map(json.loads, (d / "memory.jsonl").read_text().splitlines()):
        rd.advance(frame)
        for request in by[frame["run"]]:
            rule = request["rule"]
            order = rd.order(rule)
            ports = [(rd.store.alias(t), op) for t, op in keys(request)]
            if any(k not in rd.store.visible for k in ports):
                continue
            for depth, role in enumerate(order):
                links = rd.iface.links(rule, order[:depth], (role,))
                if not links:
                    continue
                for plan in plans(rd, rule, depth, chains):
                    prev, col, _, right = links[0]
                    direct = rd.index.rows[ports[prev]][2][col]
                    target = ports[role]
                    tab = rd.index.rows[target][0]
                    # The offline training ledger records addresses inspected
                    # by this LSH route, including collisions.
                    domain = sorted(rd.index.buckets[tab, right, direct])
                    if target not in domain:
                        continue
                    target_key = rd.index.keys[target][plan.output_column]
                    alternatives = torch.stack(
                        [rd.index.keys[k][plan.output_column] for k in domain]
                    )
                    features = route_features(
                        len(rd.live[tab]), torch.tensor([len(domain)]), depth, plan
                    )[0]
                    examples.append(
                        (features, target_key, alternatives, len(plan.steps))
                    )
    return examples


def utilities(rows, net):
    feats = torch.stack([x for x, _, _, _ in rows])
    rewards = []
    for _, q, candidates, nops in rows:
        savings = len(candidates) - int((net.code(candidates) == net.code(q)).sum())
        # One paid compute request plus one evidence encoding; this is a
        # training proxy in candidate visits, not measured runtime credit.
        rewards.append(float(savings - nops - 1))
    return feats, torch.tensor(rewards)


def fit(root, chains=False):
    from txn_chain_corpus import CHAIN_TRAIN, CHAIN_VALID

    train_cases = TRAIN + list(CHAIN_TRAIN) if chains else TRAIN
    validation = CHAIN_VALID if chains else VALID
    torch.manual_seed(12931)
    train = []
    counts = {}
    for i, case in enumerate(train_cases):
        x = examples(root, case, 967 + i, chains)
        train += x
        counts[case] = len(x)
    val = examples(root, validation, 971, chains)
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    net = TransactionNet()
    positives = []
    negs = []
    for _, q, bank, _ in train:
        other = bank[(bank != q).any(1)]
        if len(other):
            positives.append(q.expand(len(other), -1))
            negs.append(other)
    pos = torch.cat(positives).to(dev)
    neg = torch.cat(negs).to(dev)
    net.to(dev)
    opt = torch.optim.AdamW(net.planes.parameters(), lr=0.005)
    for _ in range(220):
        ix = torch.randint(len(pos), (128,))
        p = (net.planes(pos[ix]) * 6).tanh()
        n = (net.planes(neg[ix]) * 6).tanh()
        # Colliding field addresses have few disagreeing bits. Optimize their
        # separation against alternatives on actually used typed postings.
        diff = (1 - p * n).mean(1)
        loss = (
            (-4 * diff).exp().mean()
            + 0.1 * p.mean(0).square().mean()
            + 0.05 * (1 - p.square()).mean()
        )
        opt.zero_grad()
        loss.backward()
        opt.step()
    net.cpu()
    x, y = utilities(train, net)
    vx, vy = utilities(val, net)
    x, y = x.to(dev), y.to(dev)
    net.to(dev)
    opt = torch.optim.AdamW(net.route.parameters(), lr=0.006)
    for _ in range(280):
        ix = torch.randint(len(x), (64,))
        pred = net.route(x[ix]).flatten()
        loss = F.smooth_l1_loss(pred, y[ix])
        opt.zero_grad()
        loss.backward()
        opt.step()
    net.cpu().eval()
    with torch.no_grad():
        pred = net.route(vx).flatten() > 0
        meta = dict(
            train=counts,
            validation=validation,
            validation_rows=len(vy),
            validation_selected=int(pred.sum()),
            validation_net_saved_visits=int(vy[pred].sum()),
            validation_always=int(vy.sum()),
            validation_reject_unprofitable=int(((vy <= 0) & ~pred).sum()),
            contrast_pairs=len(pos),
            steps=[220, 280],
            device=dev,
            seed=12931,
        )
    out = root / ("txn-chain-study" if chains else "txn-study")
    out.mkdir(exist_ok=True)
    torch.save(net.state_dict(), out / "model.pt")
    (out / "training.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(meta)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    torch.set_num_threads(1)
    p.add_argument("--chains", action="store_true")
    a = p.parse_args()
    fit(a.root, a.chains)
