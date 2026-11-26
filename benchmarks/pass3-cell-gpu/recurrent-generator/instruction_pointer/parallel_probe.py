"""Offline twin perturbation on known native bindings; no copies enter performance runs."""

import json
from collections import Counter

import numpy as np
import torch

from discrete_draft import plan
from draft_multitarget import snapshots
from metal_scaling import CASES
from parallel_budget import args
from parallel_memory import make_memory
from parallel_trial import install


@torch.no_grad()
def run(a):
    rows = []
    for case in CASES:
        for arm in ("editor", "flow"):

            def setup(a, d, arm=arm):
                m = make_memory(a, d)
                m.probe = install(a, m, arm, 16)[2]
                return m

            bins = set()
            for m, r, g in snapshots(a, case, "teacher", setup):
                b = min(3, (len(g).bit_length() - 1) // 2)
                if b in bins:
                    continue
                bins.add(b)
                cell = next(iter(g))
                for steps in (1, 2, 4, 8):
                    m.probe.history.zero_()
                    items = m.probe.sample(
                        m,
                        plan([cell, cell]),
                        steps,
                        np.random.default_rng(43 + r),
                        Counter(),
                    )
                    cells = [i.cell for i in items]
                    rows.append(
                        {
                            "case": case,
                            "run": r,
                            "arm": arm,
                            "steps": steps,
                            "copies": cells.count(cell),
                            "hits": len(set(cells) & g.keys()),
                            "total": len(cells),
                        }
                    )
    (a.out / "twins.json").write_text(json.dumps(rows) + "\n")


if __name__ == "__main__":
    torch.set_num_threads(1)
    run(args().parse_args())
