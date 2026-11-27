"""Native paid-prefix frontiers comparisons, outside the online policy."""

import itertools
import json
import math
import os

import torch

from cell_kv_runtime import native
from constructible_study import TracePolicy
from foundation_fit import model
from foundation_world import CATS, folder, world
from partner_index_worlds import args


def flatten(p):
    return [token for _, items in p.pages for token in items]


def trajectory(a, n, w, cat, seed, i, draw):
    out = []

    def execute(cap):
        n.static_cache.clear()
        policy = TracePolicy(n, True)
        z = native(
            a,
            w,
            seed=draw,
            receipt_memory=True,
            submit_pages=2,
            policy=policy,
            slots=12,
            paid_limit=cap,
            receipt_log=policy,
        )
        return z, flatten(policy)

    final, actions = execute(None)
    end = final["stats"]["paid"]
    cache = {end: (final, actions)}

    def probe(cap):
        if cap not in cache:
            z, p = execute(cap)
            if actions[: len(p)] != p:
                raise ValueError("budget changed the named autonomous prefix")
            cache[cap] = (z, p)
        return cache[cap][0]

    for threshold in (0.25, 0.4, 0.6):
        goal = math.ceil(threshold * final["reference"])
        record = {
            "cat": cat,
            "seed": seed,
            "i": i,
            "draw": draw,
            "threshold": threshold,
            "goal": goal,
            "total_paid": end,
            "total_decisions": len(actions),
            "end_facts": final["covered"],
            "reached": final["covered"] >= goal,
        }
        if record["reached"]:
            lo, hi = 0, end
            while lo < hi:
                mid = (lo + hi) // 2
                if probe(mid)["covered"] >= goal:
                    hi = mid
                else:
                    lo = mid + 1
            z = probe(lo)
            previous = probe(lo - 1)["covered"] if lo else 0
            assert previous < goal <= z["covered"]
            record.update(
                paid=z["stats"].get("paid", 0),
                decisions=len(cache[lo][1]),
                facts=z["covered"],
                previous=previous,
            )
        out.append(record)
    ordered = sorted(cache)
    for x, y in itertools.pairwise(ordered):
        if not {str(t) for t in cache[x][0]["facts"]} <= {
            str(t) for t in cache[y][0]["facts"]
        }:
            raise ValueError("nonmonotone native fact sets")
    return out


def run(a, cat, seed):
    root = folder(a)
    n = model(a, seed, 32)
    n.load_state_dict(
        torch.load(root / f"model-{cat}-12-32-{seed}.pt", weights_only=True)
    )
    out = []
    for i in range(4):
        w = world(a, n.actor, i, False, cat)
        for draw in (193, 827):
            out.extend(trajectory(a, n, w, cat, seed, i, draw))
    (root / f"frontier-{cat}-{seed}.json").write_text(json.dumps(out))


if __name__ == "__main__":
    torch.set_num_threads(1)
    a = args()
    with torch.no_grad():
        for cat in os.getenv("FC_CATS", " ".join(CATS)).split():
            for seed in (71, 113):
                path = folder(a) / f"frontier-{cat}-{seed}.json"
                if not path.exists():
                    run(a, cat, seed)
