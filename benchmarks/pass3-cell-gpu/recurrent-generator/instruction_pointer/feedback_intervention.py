"""Seed one independently verified omission at the first stall, then use the same policy."""

import json
import os

import torch

from cell_kv_runtime import native
from cell_kv_world import World
from cell_transaction import STATUS
from competition_draw import Policy
from competition_egg import egg
from feedback_stall import folder
from partner_index_worlds import args
from selected_cell_study import store
from state_transition_corpus import Replay
from state_transition_train import load


def run(a, case):
    root = folder(a)
    audit = json.loads((root / f"stall-{case}.json").read_text())
    window = next(r for r in audit["audits"] if r["index"] == audit["first"])
    hit = next(t for t in window["probes"] if t["gained"])
    tid, refs = hit["token"]
    token = (tid, tuple(map(tuple, refs)))
    d, align = egg(a, case)
    net = load(a, "transition", 71)
    w = World(d, net.actor, entry_table=None, sides="")

    class Intervention(Policy):
        def generate(self, w, s, rng, slots):
            draws = super().generate(w, s, rng, slots)
            if s["run"] == window["run"]:
                assert not draws
                return [token]
            return draws

    baseline = []
    x = native(
        a, w, policy=Policy(net), receipt_log=baseline, seed=193, reference=align
    )
    observed = []
    y = native(
        a, w, policy=Intervention(net), receipt_log=observed, seed=193, reference=align
    )
    j = audit["first"]
    assert baseline[:j] == observed[:j] and baseline[j][0] == observed[j][0]
    assert observed[j][2][0][1] == 0
    rescheduled = [s["run"] for s, _, _ in baseline[j + 1 :] if tid in s["menu"]]
    retry = None
    if rescheduled:
        ix = next(
            k for k, (s, _, _) in enumerate(baseline) if s["run"] == rescheduled[0]
        )
        logger = []
        z = native(
            a,
            w,
            policy=Replay(baseline[:ix], [token]),
            receipt_log=logger,
            seed=193,
            reference=align,
        )
        idle = native(a, w, policy=Replay(baseline[:ix], []), seed=193, reference=align)
        assert logger[:ix] == baseline[:ix] and logger[ix][0] == baseline[ix][0]
        retry = {
            "run": rescheduled[0],
            "status": STATUS[logger[ix][2][0][1]],
            "gained": sorted(set(z["facts"]) - set(idle["facts"])),
        }
    signal = observed[j + 1][0]["ports"]
    uid = observed[j][2][0][0]
    published = [p[0] for p in signal if p[0][0] == uid]
    store(
        root / f"intervention-{case}.json",
        {
            "token": token,
            "run": window["run"],
            "immediate": hit["gained"],
            "next_publication": published,
            "rescheduled": rescheduled,
            "retry": retry,
            "original": x["covered"],
            "intervened": y["covered"],
            "gained": sorted(set(y["facts"]) - set(x["facts"])),
            "lost": sorted(set(x["facts"]) - set(y["facts"])),
        },
    )


if __name__ == "__main__":
    torch.set_num_threads(1)
    a = args()
    with torch.no_grad():
        for case in os.getenv("FB_CASES", "fact loopfact sum-divisors").split():
            run(a, case)
