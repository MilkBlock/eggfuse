"""Common-state offline audit. Archived legal targets never enter the sampler."""

import json

import torch

from cell_kv_runtime import native
from cell_kv_world import World
from competition_draw import Policy
from competition_egg import egg
from constructible_study import directory
from feedback_data import public
from feedback_stall import folder
from feedback_train import get
from partner_index_worlds import args


class Original(Policy):
    def generate(self, w, s, rng, slots):
        return super().generate(w, public(s), rng, slots)


def run(a, case):
    data = json.loads((folder(a) / f"stall-{case}.json").read_text())
    old = get(a, "old", 71)
    d, align = egg(a, case)
    w = World(d, old.actor, entry_table=None, sides="")
    history = []
    native(
        a,
        w,
        policy=Original(old),
        reference=align,
        seed=193,
        receipt_log=history,
        receipt_memory=True,
    )
    models = [("original", old), ("visible", get(a, "visible", 71))]
    rows = []
    for rec in data["audits"]:
        s, ts, _rs = history[rec["index"]]
        assert rec["run"] == s["run"] and json.loads(json.dumps(ts)) == rec["actions"]
        probes = rec["probes"]
        for label, net in models:
            net.prepare(w)
            for condition in [False, True]:
                net.condition_on_types = condition
                m = net.state(w, public(s) if label == "original" else s)
                hits = []
                for r in probes:
                    tid, refs = r["token"]
                    p = float(
                        (-net.token_loss(w, m, (tid, tuple(map(tuple, refs))))).exp()
                    )
                    if label == "original" and not condition:
                        assert abs(p - r["p"]) < 1e-6
                    hits.append(
                        {
                            "tid": tid,
                            "p": p,
                            "refs": refs,
                            "new": len(r["gained"]),
                            "status": r["reason"],
                        }
                    )
                rows.append(
                    {
                        "case": case,
                        "run": s["run"],
                        "label": label,
                        "condition": condition,
                        "compatible": sum(bool(n) for n in rec["domains"].values()),
                        "menu": len(s["menu"]),
                        "exhaustive": rec["exhaustive"],
                        "probes": hits,
                    }
                )
    (directory(a) / f"fork-{case}.json").write_text(json.dumps(rows))


if __name__ == "__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        for name in ("fact", "loopfact", "sum-divisors"):
            run(args(), name)
