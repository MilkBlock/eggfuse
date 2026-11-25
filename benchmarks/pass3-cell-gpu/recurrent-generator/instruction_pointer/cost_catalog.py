"""Discover and freeze contracts on the donor, label evaluation oracles separately."""

import argparse
from pathlib import Path

import numpy as np

from protocol_experiment import dump
from recursive_train import folder, read
from ripsat_layout import signatures


def prepare(data, store, case, discover=False):
    if discover and case != "sum":
        raise ValueError("only sum-bits may build the policy catalog")
    program = read(folder(data, case) / "program.json")
    sig = signatures(program)
    z = np.load(store / f"{case}-ledger.npz")
    meta = z["meta"]
    avoid = z["depth"][:, :, 2].sum(1)
    selected = np.flatnonzero((meta[:, 6] == 1) & (avoid > 0))
    from collections import Counter

    total = Counter()
    sample = {}
    for i in selected:
        r, j = meta[i, 1:3]
        key = (sig[r], int(j))
        total[key] += int(avoid[i])
        if key not in sample or avoid[sample[key]] < avoid[i]:
            sample[key] = i
    if discover:
        # Charge index construction before admitting a donor contract below.
        # Shortlist the top 16 measured rule/Entry pairs, independently of their depth.
        dump(store / "cost-book.json", {"training": "sum", "entries": [k for k, n in total.most_common(16)]})
    entries = set(map(tuple, read(store / "cost-book.json")["entries"]))
    valid = [i for i in selected if (sig[meta[i, 1]], int(meta[i, 2])) in entries]
    single = [sample[k] for k in sorted(entries & sample.keys())]
    sha = program["recipe"]["sha256"]
    for mode, ids in (("single", single), ("oracle", valid), ("wide", selected)):
        np.savez_compressed(store / f"{sha}-{mode}.npz", events=meta[np.asarray(ids, dtype=int), :6])
    return single


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("data", type=Path)
    p.add_argument("store", type=Path)
    p.add_argument("case")
    p.add_argument("--discover", action="store_true")
    a = p.parse_args()
    prepare(a.data, a.store, a.case, a.discover)
