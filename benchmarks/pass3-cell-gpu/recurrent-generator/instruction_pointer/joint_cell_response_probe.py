"""Frozen public state and weights; ablate only receipt rows, with no runtime pruning."""

import json
import math

import torch

from cell_kv_world import World
from competition_egg import egg
from joint_cell_corpus import folder, read_rows
from joint_cell_train import CASES, fitted
from partner_index_worlds import args


def run(a):
    result = []
    for case in CASES:
        n = fitted(a, case, "expanded", 71)
        w = World(egg(a, case)[0], n.actor, entry_table=None, sides="")
        n.prepare(w)
        for s, targets in read_rows(folder(a) / f"{case}-autonomous.pkl.gz"):
            on = n.state(w, s)
            off = n.state(w, dict(s, request_receipts=()))
            recent = {}
            for run, epoch, tid, refs, reply in reversed(s["request_receipts"]):
                if tid in on["families"] and all(ref in on["pos"] for ref in refs):
                    recent.setdefault((tid, refs), (run, reply[1]))
                    if len(recent) >= 16:
                        break
            for target in sorted(set(recent) | set(targets)):
                a1 = -float(n.token_loss(w, on, target))
                a0 = -float(n.token_loss(w, off, target))
                result.append(
                    dict(
                        case=case,
                        run=s["run"],
                        history=len(s["request_receipts"]),
                        target=target,
                        previous=recent.get(target),
                        productive=target in targets,
                        p=math.exp(a1),
                        p_blind=math.exp(a0),
                        delta_logp=a1 - a0,
                    )
                )
    (folder(a) / "response-probe.json").write_text(json.dumps(result))


if __name__ == "__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        run(args())
