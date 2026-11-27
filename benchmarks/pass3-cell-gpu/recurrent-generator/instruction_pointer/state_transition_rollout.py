"""Offline auditing of each evaluated policy's own visited states, after free execution."""

import os
import pickle
from itertools import product
from pathlib import Path

import torch

from cell_kv_runtime import native
from competition_draw import Policy
from competition_results import table
from partner_index_worlds import args
from state_transition_corpus import folder, verify, world
from state_transition_measure import mass, score
from state_transition_train import load


def run(a, d):
    rows = []
    paths = []
    for arm, weight in product(("frozen", "teacher", "transition"), (71, 113)):
        net = load(a, arm, weight)
        for i in range(6):
            w = world(a, net.actor, i, False)
            for mode in ("iid", "unique"):
                log = []
                pubs = []
                outcome = native(
                    a,
                    w,
                    seed=193,
                    policy=Policy(net, mode == "unique"),
                    receipt_log=log,
                    publication_log=pubs,
                )
                paths.append((arm, weight, i, mode, log, pubs, outcome))
                for j, (s, tokens, replies) in enumerate(log):
                    row = verify(a, w, 193, log[:j])
                    assert row["state"] == s
                    p, _ = score(w, net, row)
                    good = {t for t, l in row["labels"].items() if l["positive"]}
                    unlock = {t for t in good if t[0] == w.outnames["Ready"]}
                    hi = {t for t in good if t[0] >= w.primitives}
                    rows.append(
                        {
                            "arm": arm,
                            "seed": weight,
                            "case": i,
                            "mode": mode,
                            "window": j,
                            "positive": len(good),
                            "effective_mass": mass(p, good),
                            "producer_mass": mass(p, unlock),
                            "higher_mass": mass(p, hi),
                            "can_produce": bool(unlock),
                            "can_use_higher": bool(hi),
                            "generated_producer": len(unlock & set(tokens)),
                            "generated_higher": len(hi & set(tokens)),
                            "verified_draws": sum(t in good for t in tokens),
                            "distinct_verified": len(good & set(tokens)),
                            "signed": len(tokens),
                            "accepted": sum(q[1] == 0 for q in replies),
                            "coverage": outcome["coverage"],
                        }
                    )
    table(d, "on-policy", rows)
    (folder(a) / "on-policy.pkl").write_bytes(pickle.dumps(paths))


if __name__ == "__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        run(args(), Path(os.getenv("RESULTS_DIR", "run-recall/state-transition")))
