"""Held-out decision states stratified by exposure to the normalized Recipe."""

import json
import random
from collections import defaultdict

import torch

from cell_kv_world import World
from competition_egg import egg
from int_parameters import StructuralBake
from joint_cell_corpus import folder, read_rows
from joint_cell_train import CASES, fitted
from partner_index_worlds import args


def run(a):
    out = folder(a)
    result = []
    for case in CASES:
        inventory = json.loads((out / f"{case}-inventory.json").read_text())
        seen = set(inventory["signatures"])
        n = fitted(a, case, "sweep", 71)
        w = World(egg(a, case)[0], n.actor, entry_table=None, sides="")
        shape = StructuralBake(w.prog)
        ids = {rid: shape.key(body) for rid, body in enumerate(w.layouts)}
        (out / f"rule-signatures-{case}.json").write_text(json.dumps(ids))
        strata = defaultdict(list)
        for src in ("teacher", "autonomous"):
            for s, ts in read_rows(out / f"{case}-{src}.pkl.gz"):
                for t in ts:
                    strata[src, ids[t[0]] in seen].append((s, t))
        for (src, trained), rows in strata.items():
            selected = random.Random(2046).sample(rows, min(48, len(rows)))
            for seed in (71, 113):
                n = fitted(a, case, "sweep", seed)
                n.prepare(w)
                for s, t in selected:
                    m = n.state(w, s)
                    lp = -float(n.token_loss(w, m, t))
                    result.append(
                        dict(
                            case=case,
                            source=src,
                            seen=trained,
                            population=len(rows),
                            run=s["run"],
                            history=len(s["request_receipts"]),
                            target=t,
                            log_probability=lp,
                            seed=seed,
                            signature=ids[t[0]],
                        )
                    )
    (out / "generalization.json").write_text(json.dumps(result))


if __name__ == "__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        run(args())
