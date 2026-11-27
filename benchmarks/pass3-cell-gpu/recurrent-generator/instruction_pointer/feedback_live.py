"""Identical fixed two-Submit windows in all arms. A new sampling page per Submit."""

import os
from itertools import product

import torch

from cell_kv_runtime import native
from cell_kv_world import World
from competition_draw import Policy
from competition_egg import egg
from feedback_stall import folder
from feedback_train import get
from partner_index_worlds import args
from selected_cell_study import store
from state_transition_corpus import world


def run(a, case):
    real = case != "mixed"
    cap = (96 if real else 12) if os.getenv("FB_FIXED_PAID") == "1" else None
    label = f"{case}-cap{cap}" if cap is not None else case
    arms = ["old", "blind", "visible"] if real else ["old", "blind", "visible", "muted"]
    nets = {
        (arm, seed): get(a, "visible" if arm == "muted" else arm, seed)
        for arm, seed in product(arms, (71, 113))
    }
    actor = next(iter(nets.values())).actor
    if real:
        d, align = egg(a, case)
        worlds = [World(d, actor, entry_table=None, sides="")]
    else:
        align = None
        worlds = [world(a, actor, i, False) for i in range(6)]
    rows = []
    for i, w in enumerate(worlds):
        for draw in (193,) if real else (193, 827):
            order = list(product(nets, ("iid", "unique")))
            for block in (0, 1):
                for (arm, seed), mode in reversed(order) if (block + i) % 2 else order:
                    net = nets[arm, seed]
                    policy = Policy(net, mode == "unique")
                    net.static_cache.clear()
                    z = native(
                        a,
                        w,
                        seed=draw,
                        slots=6,
                        paid_limit=cap,
                        submit_pages=2,
                        reference=align,
                        policy=policy,
                        receipt_memory=arm == "visible",
                    )
                    rows.append(
                        dict(
                            arm=arm,
                            seed=seed,
                            mode=mode,
                            draw=draw,
                            block=block,
                            index=i,
                            attempts=policy.slots,
                            **z,
                        )
                    )
                store(folder(a) / f"live-{label}.json", rows)
                print(label, i, draw, block, len(rows), flush=True)


if __name__ == "__main__":
    torch.set_num_threads(1)
    a = args()
    with torch.no_grad():
        for case in os.getenv("FB_CASES", "mixed fact loopfact sum-divisors").split():
            run(a, case)
