"""Train first-read routing on paired traversals of random two-parent memories."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import random

import torch


def bank(rng, domain):
    n = rng.choice((2, 5, 9, 15, 16, 32, 64, 128, 256))
    fresh = rng.choice((0, .01, .1, .5, 1))
    return [(rng.choice(domain), rng.random() < fresh) for _ in range(n)]


def features(rows):
    fresh = sum(f for _, f in rows)
    return [math.log1p(len(rows)), math.log1p(fresh), int(fresh == 0), int(len(rows) < 16)]


def visits(left, right):
    masks = [[set() for _ in range(4)] for _ in range(2)]
    pages = Counter()
    fresh_count = 0
    for code, fresh in right:
        for k in range(4):
            field = (code >> (5*k)) & 31
            masks[0][k].add(field)
            if fresh:
                masks[1][k].add(field)
        fresh_count += fresh
        pages[code >> 20] += 1
    if fresh_count == 0 and not any(f for _, f in left):
        return 0
    cost = 0
    for code, fresh in left:
        if not (fresh or fresh_count):
            continue
        cost += 1
        if all((code >> (5*k)) & 31 in mask for k, mask in enumerate(masks[int(not fresh)])):
            candidates = pages[code >> 20] if len(right) >= 16 else len(right)
            cost += candidates if fresh else min(fresh_count, candidates)
    return cost


def sample(seed, count, all_fresh=False):
    rng = random.Random(seed)
    features_batch, costs = [], []
    for _ in range(count):
        domain = [rng.getrandbits(30) for _ in range(rng.choice((8, 32, 128)))]
        a, b = bank(rng, domain), bank(rng, domain)
        if all_fresh:
            a = [(code, True) for code, _ in a]
            b = [(code, True) for code, _ in b]
        features_batch.append([features(a), features(b)])
        costs.append([visits(a, b), visits(b, a)])
    return torch.tensor(features_batch), torch.tensor(costs)


def fit(x, costs, seed, width=16, steps=600):
    torch.manual_seed(seed)
    if width:
        model = torch.nn.Sequential(torch.nn.Linear(8, width), torch.nn.Tanh(), torch.nn.Linear(width, 1))
    else:
        model = torch.nn.Linear(8, 1)
    opt = torch.optim.Adam(model.parameters(), lr=.01)
    for _ in range(steps):
        idx = torch.randint(len(x), (256,))
        prob = scores(model, x[idx]).softmax(1)
        loss = (prob * costs[idx]).sum(1).mean()
        opt.zero_grad()
        loss.backward()
        opt.step()
    return model


def scores(model, x):
    return torch.cat([model(torch.cat((x[:, i], x[:, 1-i]), 1)) for i in (0, 1)], 1)


def main(out, report, ablate, smaller_control):
    torch.set_num_threads(1)
    training = sample(1703, 4096)
    model = fit(*training, 1703)
    x, costs = sample(1709, 2048)
    def total(indices):
        return int(costs.gather(1, indices[:, None]).sum())
    def evaluate(policy):
        return total(scores(policy, x).argmax(1))
    result = dict(train=4096, test=2048, seed=1703, source=int(costs[:, 0].sum()),
                  smaller=total(x[:, :, 0].argmin(1)), learned=evaluate(model),
                  oracle=int(costs.min(1).values.sum()))
    if ablate:
        fresh_training = sample(1703, 4096, all_fresh=True)
        result["ablation"] = {}
        for name, width, steps, data in [
                ("linear", 0, 600, training), ("short", 16, 40, training),
                ("all_fresh", 16, 600, fresh_training), ("wide", 64, 600, training),
                ("reference", 16, 600, training)]:
            result["ablation"][name] = [evaluate(fit(*data, seed, width, steps))
                                         for seed in (1703, 1709)]
    params = dict(weights=model[0].weight.tolist(), bias=model[0].bias.tolist(),
                  out=model[2].weight[0].tolist())
    base = json.loads(Path(__file__).with_name("model.json").read_bytes())
    out.write_text(json.dumps(dict(**base, order=params), indent=2)+"\n")
    if smaller_control:
        weights = [[0.] * 8 for _ in range(16)]
        weights[0][0], weights[0][4] = -1., 1.
        smaller = dict(weights=weights, bias=[0.] * 16, out=[1.] + [0.] * 15)
        smaller_control.write_text(json.dumps(dict(**base, order=smaller), indent=2)+"\n")
    report.write_text(json.dumps(result, indent=2)+"\n")
    print(result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--ablate", action="store_true")
    parser.add_argument("--smaller-control", type=Path)
    args = parser.parse_args()
    main(args.out, args.report, args.ablate, args.smaller_control)
