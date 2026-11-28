"""Fixed training-state audit; all selected named targets were exposed by the 100K fork."""

import gzip
import math
import os
import pickle
import random
from collections import defaultdict

import torch

from exposure_train import output
from learning_entropy import size_group, table
from partner_index_worlds import args
from scaling_archive import directory
from scaling_fit import model
from scaling_pool import Pool
from teacher_forcing import complete_nll


def run(a, name):
    start = directory(a) / "fits/local-s71-t100000"
    n, _ = model(a, {"arm": "A"}, 71)
    weights = output(a) / (name + ".pt") if "/" in name else start.with_suffix(".pt")
    n.load_state_dict(torch.load(weights, weights_only=True))
    n.eval()
    p = Pool(a, n)
    with gzip.open(start.with_suffix(".seen.gz"), "rb") as f:
        seen = pickle.load(f)
    bins = defaultdict(list)
    for key, names in sorted(seen.items()):
        bins[size_group(len(names))].append(key)
    rng = random.Random(90413)
    rows = []
    for group, keys in sorted(bins.items()):
        for key in rng.sample(keys, min(80, len(keys))):
            w, s, available = p.row(key)
            names = sorted(seen[key])
            assert set(names) <= set(available)
            losses = torch.cat(
                [
                    complete_nll(n, [(w, s, names[i : i + 128])])
                    for i in range(0, len(names), 128)
                ]
            ).double()
            ce = float(losses.mean())
            h = math.log(len(names))
            rows.append(
                {
                    "program": key[0],
                    "state": key[1],
                    "group": group,
                    "k": len(names),
                    "ce": ce,
                    "h": h,
                    "excess": ce - h,
                }
            )
    table("train-probe-" + name.replace("/", "_") + ".csv", rows)


if __name__ == "__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        run(args(), os.environ["EXPOSURE_MODELS"])
