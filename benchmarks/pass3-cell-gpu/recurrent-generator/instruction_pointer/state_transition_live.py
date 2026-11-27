"""Fixed-exit autonomous native runs; the oracle is absent during generation."""

import os
from itertools import product

import torch

from cell_kv_runtime import native
from cell_kv_world import World
from competition_draw import Policy
from competition_egg import egg
from partner_index_worlds import args
from selected_cell_study import store
from state_transition_corpus import folder, world
from state_transition_train import load


class SlotBudget(Policy):
    def __init__(self, net, unique, limit=None):
        super().__init__(net, unique)
        self.limit = limit
        self.offered = 0

    def generate(self, w, state, rng, slots):
        if not state["menu"]:
            return []
        available = (
            slots if self.limit is None else min(slots, self.limit - self.offered)
        )
        self.offered += available
        return super().generate(w, state, rng, available) if available else []


def run(a, case):
    real = case != "mixed"
    arms = ("frozen", "transition") if real else ("frozen", "teacher", "transition")
    nets = {(m, k): load(a, m, k) for m, k in product(arms, (71, 113))}
    actor = next(iter(nets.values())).actor
    if real:
        d, align = egg(a, case)
        worlds = [World(d, actor, entry_table=None, sides="")]
        budgets = [(6, 64), (6, 192), (6, None)]
        seeds = (193,)
    else:
        worlds = [world(a, actor, i, False) for i in range(6)]
        align = None
        budgets = [(2, None), (6, None), (6, 6), (6, 18)]
        seeds = (193, 827)
    if os.getenv("TRANS_IDLE") == "1":
        net = next(iter(nets.values()))
        results = [
            native(a, w, seed=193, slots=0, policy=Policy(net), reference=align)
            for w in worlds
        ]
        assert all(x["stats"]["paid"] == 0 for x in results)
        store(folder(a) / f"idle-{case}.json", results)
        return
    global_slots = os.getenv("TRANS_GLOBAL") == "1"
    trials = (
        [(6, None, n) for n in ((96, 384) if real else (6, 18))]
        if global_slots
        else [(s, c, None) for s, c in budgets]
    )
    rows = []
    for i, w in enumerate(worlds):
        for slots, cap, limit in trials:
            for draw in seeds:
                order = list(product(nets, ("iid", "unique")))
                for block in range(2):
                    for (arm, seed), mode in (
                        reversed(order) if (block + i) % 2 else order
                    ):
                        net = nets[arm, seed]
                        net.static_cache.clear()
                        policy = SlotBudget(net, mode == "unique", limit)
                        result = native(
                            a,
                            w,
                            seed=draw,
                            slots=slots,
                            paid_limit=cap,
                            policy=policy,
                            reference=align,
                        )
                        assert cap is None or result["stats"]["paid"] <= cap
                        rows.append(
                            dict(
                                case=case,
                                index=i,
                                seed=seed,
                                draw=draw,
                                block=block,
                                arm=arm,
                                mode=mode,
                                slots=slots,
                                cap=cap,
                                slot_limit=limit,
                                offered=policy.offered,
                                attempts=policy.slots,
                                calls=policy.calls,
                                **result,
                            )
                        )
            store(
                folder(a) / f"live-{case}{'-slots' if global_slots else ''}.json", rows
            )
            print(case, i, slots, cap, len(rows), flush=True)


if __name__ == "__main__":
    torch.set_num_threads(1)
    a = args()
    with torch.no_grad():
        for case in os.environ["TRANS_CASES"].split():
            run(a, case)
