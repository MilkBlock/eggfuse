"""Offline inference interventions on states actually reached by the EggCC A policy."""

import json
import os
from pathlib import Path

import torch

from cell_kv_runtime import native
from cell_kv_world import World
from competition_egg import egg
from constructible_study import TracePolicy
from foundation_egg_catalogue import install
from foundation_fit import model
from partner_index_worlds import args
from region_bake import linked
from trigger_training import MODES, directory


class SampledPages:
    def __init__(self):
        self.rows = []
        self.last = None

    def append(self, record):
        state, _, _ = record
        run = state["run"]
        if run != self.last and (run <= 32 or run % 32 == 0):
            self.rows.append(state)
        self.last = run


def main(a, case):
    ir, align = egg(a, case)
    donor = json.loads(
        (Path(os.environ["ARTIFACT_ROOT"]) / "region-owner-1126/menu.json").read_text()
    )
    out = directory(a)
    models = {}
    for mode in MODES:
        n = model(a, 71, 32)
        n.load_state_dict(torch.load(out / f"{mode}-71.pt", weights_only=True))
        n.rule_condition = mode
        n.eval()
        n.physical = ("held", 0)
        models[mode] = n
    w = World(ir, n.actor, entry_table=None, sides="")
    install(w, linked(w.prog, donor), "multi")
    target = SampledPages()
    pol = TracePolicy(models["none"], True)
    z = native(
        a,
        w,
        policy=pol,
        receipt_log=target,
        receipt_memory=True,
        slots=6,
        submit_pages=2,
        seed=193,
        reference=align,
        rule_state=True,
    )
    rows = []
    for mode, n in models.items():
        n.prepare(w)
        for s in target.rows:
            if not s["menu"]:
                continue
            flags = s["rule_state"]
            keys = list(flags)
            perm = dict(zip(keys, keys[1:] + keys[:1], strict=True))
            for intervention in ("real", "cycle_dirty", "mute_wm"):
                fields = {
                    r: (
                        0 if intervention == "mute_wm" else wm,
                        flags[perm[r]][1] if intervention == "cycle_dirty" else d,
                    )
                    for r, (wm, d) in flags.items()
                }
                m = n.state(w, dict(s, rule_state=fields))
                lp = m["root_lp"]
                active = lp.new_tensor([float(flags[r][1]) for r in m["families"]])
                support = lp.isfinite()
                if not support.any():
                    continue
                rows.append(
                    {
                        "case": case,
                        "run": s["run"],
                        "epoch": s["epoch"],
                        "mode": mode,
                        "intervention": intervention,
                        "check": s["check_dirty"],
                        "families": len(lp),
                        "supported": int(support.sum()),
                        "active_supported": int((active * support).sum()),
                        "p_active": float((lp.exp() * active).sum()),
                    }
                )
    (out / f"snapshots-{case}.json").write_text(
        json.dumps({"graph": z["graph"], "rows": rows})
    )


if __name__ == "__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        main(args(), os.environ["TR_CASE"])
