"""Compute native corpus counts and multidimensional difficulty once, offline."""

import gzip
import json
import pickle
from collections import Counter

import torch

from joint_cell_train import fitted
from partner_index_worlds import args
from scaling_archive import directory
from scaling_pool import Pool


def run(a):
    p = Pool(a, fitted(a, "sum-divisors", "sweep", 0))
    features = {}
    counts = Counter()
    kinds = Counter()
    for key in p.keys:
        w, s, ts = p.row(key)
        refs = Counter(port[3] for port in s["ports"])
        arity = max(len(t[1]) for t in ts)
        domain = max(
            (refs[ty] for t, _ in ts for ty in w.roles[w.layouts[t][0][0]]), default=0
        )
        depth = max(len(w.layouts[t]) for t, _ in ts)
        dims = [
            domain,
            len(s["menu"]),
            arity,
            len(ts),
            depth,
            len(s.get("request_receipts", ())),
            s["epoch"],
        ]
        features[key] = dims
        counts["states"] += 1
        counts["state_named_token"] += len(ts)
        counts["effect_identity_known_targets"] += len(p.effects.get(key, {}))
        counts["state_verified_effect_sets"] += len(
            set(p.effects.get(key, {}).values())
        )
        for tid, rr in ts:
            kinds[len(rr), len(w.layouts[tid])] += 1
    d = directory(a)
    with gzip.open(d / "difficulty.pkl.gz", "wb") as f:
        pickle.dump(features, f)
    (d / "inventory.json").write_text(
        json.dumps(
            {
                "counts": counts,
                "arities_and_sizes": {str(k): v for k, v in kinds.items()},
                "programs": len(p.programs),
                "sources": {s: len(v) for s, v in p.collections.items()},
                "manifest": p.catalogue_digest,
            }
        )
    )


if __name__ == "__main__":
    torch.set_num_threads(1)
    run(args())
