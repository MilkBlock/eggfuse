"""Print one witness's actual split intervals and both named pivot addresses."""

import gzip
import json

import torch

from draft_multitarget import snapshots
from parallel_budget import args


def explain(keys, target, prob):
    lo, hi = 0, len(keys)
    idx = keys.index(target)
    rows = []
    for p in prob:
        mid = (lo + hi) // 2
        rows.append(
            {
                "lo": lo,
                "hi": hi,
                "mid": mid,
                "left_pivot": keys[(lo + mid - 1) // 2],
                "right_pivot": keys[(mid + hi - 1) // 2],
                "go_right": idx >= mid,
                "conditional_branch": p,
            }
        )
        if idx >= mid:
            lo = mid
        else:
            hi = mid
    assert lo == idx and hi == idx + 1
    return rows


@torch.no_grad()
def run(a):
    with gzip.open(a.out / "paths-original.jsonl.gz", "rt") as f:
        witness = next(
            x
            for l in f
            if (x := json.loads(l))["case"] == "sum-divisors"
            and any(s.get("domain", 0) >= 1024 for s in x["steps"][1:])
        )
    for m, r, g in snapshots(a, witness["case"], "teacher"):
        if r != witness["run"]:
            continue
        rule = witness["rule"]
        for j, s in enumerate(witness["steps"]):
            keys = m.ids if not j else m.rows[m.roles[rule][j - 1]]
            target = (rule, False) if not j else tuple(witness["refs"][j - 1][:2])
            s["splits"] = explain(keys, target, s["path"])
        (a.out / "worked-example.json").write_text(json.dumps(witness, indent=2) + "\n")
        return
    raise AssertionError("missing audited state")


if __name__ == "__main__":
    torch.set_num_threads(1)
    run(args().parse_args())
