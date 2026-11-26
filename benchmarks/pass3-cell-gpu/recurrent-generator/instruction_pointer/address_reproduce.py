"""Replay the exact original CPU draw order; compare addresses and native binding identities."""

import json
from collections import Counter

import numpy as np
import torch

from address_verdicts import Probes
from draft_multitarget import snapshots
from metal_scaling import CASES, models
from parallel_budget import args


@torch.no_grad()
def run(a):
    marks, _ = models("1M")
    marks.load_state_dict(
        torch.load(a.previous / "s243/1M-n1000000/weights.pt", weights_only=True)[0]
    )
    old = {
        (x["case"], x["run"]): x
        for x in json.loads((a.out / "audit-draws.json").read_bytes())
        if x["budget"] == 256
    }
    rows = []
    for case in CASES:
        probe = Probes(a, case, "frozen-cpu-159")
        for m, r, g in snapshots(a, case, "teacher"):
            rng = np.random.default_rng(536 + r)
            for n in (4, 16, 64, 256):
                seen = set()
                for draw in range(n):
                    c = marks.draw(m, rng, Counter())
                    if n == 256 and c is not None:
                        seen.add(c)
                        probe.add(
                            r,
                            c,
                            (next(b for b in (4, 16, 64, 256) if b > draw), c.higher),
                        )
                if n == 256:
                    assert len(seen & g.keys()) == old[case, r]["hits"]
        for row in probe.score():
            rows.append(dict(case=case, **row))
    (a.out / "original-native-recall.json").write_text(json.dumps(rows) + "\n")


if __name__ == "__main__":
    torch.set_num_threads(1)
    run(args().parse_args())
