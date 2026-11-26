"""Substitute one equal-key live address at a time and replay the complete certificate."""

import json
from collections import defaultdict

import numpy as np
import torch

from address_verdicts import Probes
from discrete_cells import from_q
from discrete_draft import Cell
from draft_multitarget import snapshots
from metal_scaling import CASES
from parallel_budget import args


def signature(row):
    return row["table"], row["version"], row["forwarded"], tuple(row["hashes"])


@torch.no_grad()
def run(a):
    rows = []
    for case in CASES:
        probe = Probes(a, case, "same-key")
        owners = {(q["run"], from_q(q)): q["token"] for q in probe.tape["requests"]}
        rng = np.random.default_rng(243)
        for m, r, g in snapshots(a, case, "teacher"):
            group = defaultdict(list)
            for addr, (row, key) in m.pub.live.items():
                group[row["table"], key.numpy().tobytes()].append(addr)
            for c in g:
                for j, ref in enumerate(c.refs):
                    row, key = m.pub.live[ref[:2]]
                    matches = group[row["table"], key.numpy().tobytes()]
                    if len(matches) < 2:
                        continue
                    i = int(rng.integers(len(matches) - 1))
                    other = matches[i] if matches[i] != ref[:2] else matches[-1]
                    alt = m.pub.live[other][0]
                    changed = (*other, alt["version"])
                    probe.add(
                        r,
                        Cell(c.rule, c.refs[:j] + (changed,) + c.refs[j + 1 :]),
                        (owners[r, c], j, signature(row) == signature(alt)),
                    )
        for r, meta, owner, reason in probe.check():
            gold, j, identical = meta
            rows.append(
                {
                    "case": case,
                    "run": r,
                    "slot": j,
                    "same_encoder_inputs": identical,
                    "native": reason,
                    "same_binding": owner == gold,
                }
            )
    (a.out / "substitutions.json").write_text(json.dumps(rows) + "\n")


if __name__ == "__main__":
    torch.set_num_threads(1)
    run(args().parse_args())
