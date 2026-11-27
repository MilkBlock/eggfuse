"""Alternate catalogues on the same workloads after training, including reference graph checks."""

import json
from itertools import product

import torch

from abstraction_catalogue import CATALOGUES, build_world
from cell_kv_runtime import native
from constructible_study import TracePolicy, directory
from feedback_train import get
from partner_index_worlds import args


def run(a):
    root = directory(a)
    rows = []
    for seed in (71, 113):
        nets = {}
        for cat in CATALOGUES:
            model = get(a, "visible", seed)
            model.load_state_dict(
                torch.load(root / f"scale-{cat}-{seed}.pt", weights_only=True)
            )
            model.condition_on_types = True
            nets[cat] = model
        for i in range(4):
            worlds = {c: build_world(a, n.actor, i, False, c) for c, n in nets.items()}
            for draw, rep in product((193, 827), range(4)):
                for cat in reversed(CATALOGUES) if rep % 2 else CATALOGUES:
                    n = nets[cat]
                    n.static_cache.clear()
                    pol = TracePolicy(n, True)
                    z = native(
                        a,
                        worlds[cat],
                        policy=pol,
                        slots=6,
                        submit_pages=2,
                        seed=draw,
                        receipt_log=pol,
                        receipt_memory=True,
                    )
                    rows.append(
                        dict(
                            cat=cat,
                            seed=seed,
                            index=i,
                            draw=draw,
                            rep=rep,
                            decisions=pol.count["signed"],
                            **z,
                        )
                    )
    (root / "abstraction-timing.json").write_text(
        json.dumps(rows, separators=(",", ":"))
    )


if __name__ == "__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        run(args())
