"""Replay the optimizer's target sampler, including partial final updates, without fitting."""

import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import torch

from exposure_train import output
from partner_index_worlds import args
from scaling_archive import directory
from scaling_fit import model
from scaling_pool import Pool, Sampler

REPORT = Path("run-recall/matched-learning")


def size_group(n):
    return "1" if n == 1 else "2-8" if n <= 8 else "9+"


def table(file, rows):
    if not rows:
        return
    REPORT.mkdir(parents=True, exist_ok=True)
    with (REPORT / file).open("w", newline="") as f:
        writer = csv.DictWriter(f, list(dict.fromkeys(k for r in rows for k in r)))
        writer.writeheader()
        writer.writerows(rows)


def main(a):
    src = directory(a) / "fits/local-s71-resume.pt"
    saved = torch.load(src, weights_only=False)
    n, _ = model(a, saved["config"], 71)
    p = Pool(a, n)
    sampler = Sampler(p, 71, saved["config"])
    sampler.rng.setstate(saved["rng"])
    emitted = 100000
    steps = saved["progress"][5]
    h = 0.0
    totals = Counter()
    states = defaultdict(set)
    raw = []
    signature = hashlib.sha256()
    for cap in (250000, 500000, 1000000):
        while emitted < cap:
            key, _, _, ts = sampler.next(1)
            m = len(ts)
            targets = ts[: cap - emitted]
            k = len(targets)
            g = size_group(m)
            signature.update(repr((key, targets)).encode())
            h += k * math.log(m)
            totals[g] += k
            states[g].add(key)
            emitted += k
            steps += 1
        fit = json.loads(
            (output(a) / "A-batched" / f"local-s71-t{cap}.json").read_text()
        )
        assert fit["steps"] == steps
        raw.append(
            dict(
                exposures=cap,
                increment=cap - 100000,
                entropy=h / (cap - 100000),
                steps=steps,
                order_sha=signature.hexdigest(),
                **{"targets_" + g: totals[g] for g in ("1", "2-8", "9+")},
                **{"states_" + g: len(states[g]) for g in ("1", "2-8", "9+")},
            )
        )
    table("sampler-entropy.csv", raw)


if __name__ == "__main__":
    torch.set_num_threads(1)
    main(args())
