"""Post-run bounds at the real quotas. Labels are available only to this diagnostic."""
import argparse
import hashlib
import json
from collections import defaultdict
from math import tanh
from pathlib import Path


def logit(weights, features):
    def affine(w, bias):
        for weight, value in zip(w, features):
            bias += weight * value / 8.
        return bias
    if "hidden" not in weights:
        return affine(weights["weights"], weights["bias"])
    score = weights["bias"]
    for w, bias, output in zip(weights["hidden"], weights["hidden_bias"], weights["output"]):
        score += tanh(affine(w, bias)) * output
    return score


def bounds(groups, model):
    """Within a tie, aggregates preserve counts but not native source order."""
    memo = {}
    lower = upper = 0
    expectation = 0.
    for _, _, grant, rows in groups:
        bins = defaultdict(lambda: [0, 0])
        for features, no, yes in rows:
            key = tuple(features)
            if key not in memo:
                memo[key] = logit(model, key)
            numbers = bins[memo[key]]
            numbers[0] += no
            numbers[1] += yes
        for _, (no, yes) in sorted(bins.items(), reverse=True):
            take = min(grant, no + yes)
            lower += max(0, take - no)
            upper += min(yes, take)
            expectation += take * yes / (no + yes)
            grant -= take
            if not grant:
                break
    return dict(lower=lower, upper=upper, random_tie_mean=expectation)


def ceilings(path, models):
    payload = path.read_bytes()
    capture = json.loads(payload)
    by_run = defaultdict(lambda: [0, 0])
    selected = local = 0
    for epoch, _, grant, rows in capture["groups"]:
        births = sum(yes for _, _, yes in rows)
        selected += min(grant, sum(n+y for _, n, y in rows))
        local += min(grant, births)
        by_run[epoch][0] += grant
        by_run[epoch][1] += births
    c = capture["counts"]
    assert selected == c["selected"] and local == c["oracle_fresh"]
    return dict(capture_sha256=hashlib.sha256(payload).hexdigest(), selected=selected,
                first=c["first_fresh"], local_oracle=local,
                per_run_oracle=sum(min(k, n) for k, n in by_run.values()),
                bounds={k: bounds(capture["groups"], m) for k, m in models.items()})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("policy", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--cases", nargs="+", default=["conjugate-gradient", "3mm"])
    args = parser.parse_args()
    models = {k: v for k, v in json.loads(args.policy.read_bytes())["models"].items() if k.endswith("-1703")}
    summary = {c: ceilings(args.directory / (c + ".json"), models) for c in args.cases}
    args.out.write_text(json.dumps(summary, indent=2) + "\n")
