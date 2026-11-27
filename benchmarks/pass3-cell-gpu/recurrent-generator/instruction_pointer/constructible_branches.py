"""Preservation test for the two verified post-publication Higher branches."""

import pickle

import torch

from competition_results import table
from constructible_study import directory
from feedback_measure import prob
from feedback_stall import folder
from feedback_train import get
from partner_index_worlds import args
from state_transition_corpus import world


def run(a):
    rows = []
    for seed in (71, 113):
        for mode in ("A", "B", "TB"):
            net = get(a, "visible", seed)
            if mode == "TB":
                net.load_state_dict(
                    torch.load(
                        directory(a) / f"structured-{seed}.pt", weights_only=True
                    )
                )
            net.condition_on_types = mode != "A"
            for i in range(6):
                w = world(a, net.actor, i, False)
                net.prepare(w)
                hits = []
                for s, v in pickle.loads((folder(a) / f"test-{i}.pkl").read_bytes())[
                    "siblings"
                ]:
                    (g,) = [t for t in v if t[0] >= w.primitives]
                    probs = prob(
                        net,
                        w,
                        s,
                        [(k, g[1]) for k in range(w.primitives, len(w.layouts))],
                    )
                    total = sum(probs.values())
                    hits.append(
                        (
                            probs[g],
                            total,
                            probs[g] > max(p for t, p in probs.items() if t != g),
                        )
                    )
                rows.append(
                    {
                        "seed": seed,
                        "mode": mode,
                        "case": i,
                        "full": sum(p for p, _, _ in hits) / 2,
                        "family": sum(t for _, t, _ in hits) / 2,
                        "conditional": sum(p / t for p, t, _ in hits) / 2,
                        "flip": all(win for _, _, win in hits),
                    }
                )
    table(directory(a), "higher", rows)


if __name__ == "__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        run(args())
