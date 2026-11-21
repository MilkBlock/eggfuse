"""Fit three whole-Run grant forecasts on frozen donor histograms using CPU PyTorch."""
import argparse
import hashlib
import json
import math
from pathlib import Path

import torch
from torch.nn import functional as F

HERE = Path(__file__).resolve().parent
DONORS = ("sum-bits", "dot-product", "jacobi-1d")
INPUT = HERE.parent / "speculative-allocation-policy/donors.json"
CAP = 8192
DTYPE = torch.float64
QUANTILES = {"balanced": 0.5, "coverage": 0.8}


def load(path):
    records = json.loads(path.read_bytes())
    if set(records) != set(DONORS):
        raise ValueError("expected exactly the three frozen donor workloads")
    batches = {}
    for donor in DONORS:
        run = records[donor]["run"]
        features, offers, fresh, frequencies = [], [], [], []
        for prior, count, winners, target, frequency in run["events"]:
            assert len(prior) == 8 and prior[0] == 1 and prior[7] == 0
            assert 0 <= target <= winners <= count and frequency > 0
            features.append([*prior[:7], math.log1p(count)])
            offers.append(count)
            fresh.append(target)
            frequencies.append(frequency)
        tensors = tuple(torch.tensor(t, dtype=DTYPE) for t in (features, offers, fresh, frequencies))
        _, n, y, m = tensors
        assert int(m.sum()) == run["total"]
        assert int(m @ n) == run["offers"] and int(m @ y) == run["fresh"]
        batches[donor] = tensors
    return batches


def predict(name, weights, x, offers):
    score = x @ weights
    if name == "fraction":
        count = offers * torch.sigmoid(score)
    else:
        count = torch.expm1(score.clamp(0, math.log1p(CAP)))
    return torch.minimum(count.clamp(max=CAP), offers)


def objective(name, weights, batch):
    x, offers, target, frequency = batch
    if name == "fraction":
        # Sum the Bernoulli losses for y fresh grants and n-y other offers.
        # Histograms have multiplicity; do not weigh tiny/empty Runs as large ones.
        score = x @ weights
        losses = target * F.softplus(-score) + (offers - target) * F.softplus(score)
        return (frequency @ losses) / (frequency @ offers)
    residual = target - predict(name, weights, x, offers)
    q = QUANTILES[name]
    return (frequency @ torch.maximum(q * residual, (q - 1) * residual)) / (frequency @ target)


def fit(name, batch):
    x, offers, target, freq = batch
    if name == "fraction":
        initial = torch.zeros(8, dtype=DTYPE)
        initial[0] = torch.logit((freq @ target) / (freq @ offers))
    else:
        gram = x.T @ (freq[:, None] * x) + 0.1 * torch.eye(8, dtype=DTYPE)
        initial = torch.linalg.solve(gram, x.T @ (freq * torch.log1p(target)))
    w = torch.nn.Parameter(initial.clone())
    opt = torch.optim.Adam([w], lr=0.01)
    best = initial.clone()
    best_loss = float(objective(name, best, batch))
    first_loss = best_loss
    for _ in range(600):
        loss = objective(name, w, batch)
        opt.zero_grad()
        loss.backward()
        opt.step()
        with torch.no_grad():
            value = float(objective(name, w, batch))
            if value < best_loss:
                best_loss, best = value, w.detach().clone()
    assert best_loss < first_loss and torch.isfinite(best).all()
    return best, {"initial_loss": first_loss, "fitted_loss": best_loss}


def counts(name, w, batch):
    x, offers, target, freq = batch
    grants = (predict(name, w, x, offers) + 0.5).floor()
    overlap = torch.minimum(grants, target)
    return {"events": int(freq.sum()), "nonempty": int(freq[offers > 0].sum()),
            "offers": int(freq @ offers), "fresh": int(freq @ target),
            "grants": int(freq @ grants), "overlap": int(freq @ overlap),
            "missed": int(freq @ (target - overlap)), "unused": int(freq @ (grants - overlap))}


def train(path):
    data = load(path)
    batch = tuple(torch.cat(parts) for parts in zip(*data.values()))
    result = {"donors": list(DONORS), "input_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
              "cap": CAP, "models": {}, "fit": {}, "training_counts": {}}
    for name in (*QUANTILES, "fraction"):
        w, losses = fit(name, batch)
        result["models"][name] = w.tolist()
        result["fit"][name] = losses
        result["training_counts"][name] = {k: counts(name, w, b) for k, b in data.items()}
        result["training_counts"][name]["total"] = counts(name, w, batch)
        print(name, losses, result["training_counts"][name]["total"], flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--donors", type=Path, default=INPUT)
    parser.add_argument("--out", type=Path, default=HERE / "policy.json")
    args = parser.parse_args()
    torch.set_num_threads(1)
    args.out.write_text(json.dumps(train(args.donors), indent=2, allow_nan=False) + "\n")
