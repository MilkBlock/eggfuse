"""Measure the frozen boundary readout on actual early EggCC decision states."""

import json
import os
from pathlib import Path

import torch

from cell_kv_runtime import native
from cell_kv_world import World
from competition_egg import egg
from foundation_egg_catalogue import install
from partner_index_worlds import args
from region_bake import linked
from trigger_execution import ExecutionTrace
from variable_completion import CompletionPolicy, boundary_input, directory, network


class Windows(CompletionPolicy):
    def __init__(self, n):
        super().__init__(n, False, None, False)
        self.rows = []

    def generate(self, w, s, rng, slots):
        cells = super().generate(w, s, rng, slots)
        if s["run"] <= 8:
            r = {
                "run": s["run"],
                "epoch": s["epoch"],
                "menu": len(s["menu"]),
                "uids": [],
            }
            if s["menu"]:
                m = self.net.state(w, s)
                if m["has_complete_domain"]:
                    r["p_end"] = float(self.net.actor.stop(boundary_input(m)).sigmoid())
                    r["probabilities"] = {
                        k: float(v.exp())
                        for k, v in zip(m["families"], m["root_lp"], strict=True)
                        if v.isfinite()
                    }
                    r["dirty"] = {k: s["rule_state"][k][1] for k in r["probabilities"]}
            self.rows.append(r)
        return cells

    def append(self, entry):
        s, _, replies = entry
        if s["run"] <= 8:
            self.rows[-1]["uids"] = [v[0] for v in replies]


def run(a, case):
    d = directory(a)
    ir, align = egg(a, case)
    for seed in (71, 113):
        n = network(a, seed)
        n.actor.stop.load_state_dict(
            torch.load(d / f"boundary-{seed}.pt", weights_only=True)
        )
        w = World(ir, n.actor, entry_table=None, sides="")
        install(
            w,
            linked(
                w.prog,
                json.loads(
                    (
                        Path(os.environ["ARTIFACT_ROOT"])
                        / "region-owner-1126/menu.json"
                    ).read_text()
                ),
            ),
            "multi",
        )
        p = Windows(n)
        audit = ExecutionTrace()
        native(
            a,
            w,
            policy=p,
            receipt_log=p,
            receipt_memory=True,
            submit_pages=2,
            slots=6,
            reference=align,
            seed=193,
            rule_state=True,
            execution_trace=audit,
            paid_limit=96,
        )
        for row in p.rows:
            row["effects_of_sampled_requests"] = [
                audit.entries[u]["effective_ops"] for u in row["uids"]
            ]
        (d / f"windows-{case}-{seed}.json").write_text(json.dumps(p.rows))


if __name__ == "__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        run(args(), os.environ["TR_CASE"])
