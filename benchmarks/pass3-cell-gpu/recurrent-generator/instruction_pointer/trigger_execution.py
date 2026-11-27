"""Native free execution, separating online observations from post-issue attribution."""

import csv
import json
import os
from collections import Counter
from pathlib import Path

import torch

from cell_kv_runtime import native
from cell_kv_world import World
from cell_transaction import STATUS
from competition_egg import egg
from constructible_study import TracePolicy
from foundation_egg_catalogue import install
from foundation_fit import model
from foundation_world import world
from partner_index_worlds import args
from region_bake import linked
from trigger_training import MODES, directory


class ExecutionTrace:
    def __init__(self):
        self.entries = {}
        self.higher = {}
        self.steps = {}

    def entry(self, w, s, tid, refs, reply):
        uid, status, *_ = reply
        rid = w.layouts[tid][0][0]
        wm, dirty = s["rule_state"][rid]
        record = {
            "uid": uid,
            "run": s["run"],
            "epoch": s["epoch"],
            "tid": tid,
            "rid": rid,
            "refs": refs,
            "wm": wm,
            "dirty": dirty,
            "check": s["check_dirty"],
            "status": STATUS[status],
        }
        self.entries[uid] = record
        if tid >= w.primitives:
            self.higher[uid] = record | {"body": len(w.layouts[tid]), "steps": []}

    def step(self, owner, j, rid, reply):
        uid, status, *_ = reply
        self.steps[uid] = (owner, j, rid, STATUS[status])
        self.higher[owner]["steps"].append(
            {"uid": uid, "j": j, "rid": rid, "status": STATUS[status]}
        )

    def finish(self, ept, path, completed):
        # The ledger is available only after the final Seal. It never enters a snapshot.
        effects = Counter()
        for uid, n in ept["origins"]:
            if uid in self.entries or uid in self.steps:
                effects[uid] += n
        if sum(effects.values()) != sum(ept["signed_external"]) + sum(
            ept["signed_internal"]
        ):
            raise ValueError("effective operations do not reconcile with paid requests")
        seen = set()
        with path.open() as f:
            for run, uid, rid, epoch, check, dirty in (
                map(int, row) for row in csv.reader(f)
            ):
                if uid in seen:
                    raise ValueError("duplicate admission observer ID")
                seen.add(uid)
                if uid in self.entries:
                    r = self.entries[uid]
                    if (run, rid, epoch, bool(check), bool(dirty)) != (
                        r["run"],
                        r["rid"],
                        r["epoch"],
                        r["check"],
                        r["dirty"],
                    ):
                        raise ValueError(
                            "issue-time native state differs from decoder snapshot"
                        )
                else:
                    assert self.steps[uid][2] == rid
        assert seen == set(self.entries) | set(self.steps)
        for uid, r in self.entries.items():
            r["effective_ops"] = effects[uid]
        for uid, r in self.higher.items():
            status = r["status"]
            r["trigger"] = (
                "disabled"
                if not r["check"]
                else "failed"
                if status == "untriggered_rule"
                else "passed"
            )
            r["binding"] = (
                "failed"
                if status == "binding"
                else "passed"
                if status
                in (
                    "accepted",
                    "duplicate",
                    "watermark",
                    "guard",
                    "unbound_primitive",
                    "unbound_input",
                )
                else "unknown"
            )
            r["guard"] = (
                "failed"
                if status == "guard"
                else "passed"
                if status in ("accepted", "duplicate", "unbound_input")
                else "unknown"
            )
            r["accepted"] = status == "accepted"
            r["completed"] = uid in completed
            for step in r["steps"]:
                step["effective_ops"] = effects[step["uid"]]
            r["internal_accepted"] = sum(
                step["status"] == "accepted" for step in r["steps"]
            )
            r["effective_ops"] = effects[uid] + sum(
                step["effective_ops"] for step in r["steps"]
            )


def run(a, case):
    out = directory(a)
    donor = json.loads(
        (Path(os.environ["ARTIFACT_ROOT"]) / "region-owner-1126/menu.json").read_text()
    )
    ir, align = egg(a, case) if case != "controlled" else (None, None)
    units = linked(json.loads((ir / "program.json").read_text()), donor) if ir else None
    for budget in ("slots", "paid", "full") if ir else ("full",):
        path = out / f"{case}-{budget}.json"
        rows = json.loads(path.read_text()) if path.exists() else []
        for seed in (71, 113):
            for rep in (-1, 0, 1):
                for mode in reversed(MODES) if rep == 1 else MODES:
                    if any(
                        (mode, seed, rep) == (r["mode"], r["seed"], r["rep"])
                        for r in rows
                    ):
                        continue
                    n = model(a, seed, 32)
                    n.load_state_dict(
                        torch.load(out / f"{mode}-{seed}.pt", weights_only=True)
                    )
                    n.rule_condition = mode
                    n.eval()
                    n.physical = ("held", 0)
                    if ir:
                        w = World(ir, n.actor, entry_table=None, sides="")
                        install(w, units, "multi")
                    else:
                        w = world(a, n.actor, 0, False, "multi")
                    pol = TracePolicy(n, True, 384 if budget == "slots" else None)
                    audit = ExecutionTrace() if rep == -1 else None
                    r = native(
                        a,
                        w,
                        policy=pol,
                        receipt_log=pol,
                        receipt_memory=True,
                        slots=6 if ir else 12,
                        submit_pages=2,
                        reference=align,
                        paid_limit=96 if budget == "paid" else None,
                        seed=193,
                        rule_state=(audit is not None or mode != "none"),
                        execution_trace=audit,
                    )
                    if audit:
                        r["higher"] = list(audit.higher.values())
                        r["entries"] = list(audit.entries.values())
                    else:
                        checked = next(
                            x
                            for x in rows
                            if x["rep"] == -1
                            and x["seed"] == seed
                            and x["mode"] == mode
                        )
                        assert all(
                            checked[k] == r[k]
                            for k in ("facts", "stats", "graph", "ops")
                        )
                    rows.append(
                        r
                        | {
                            "mode": mode,
                            "seed": seed,
                            "rep": rep,
                            "case": case,
                            "budget": budget,
                            "slots": pol.count["offered"],
                            "calls": pol.count["distribution_reads"],
                            "decode": pol.decode_s,
                            "prepare": pol.prepare_s,
                        }
                    )
                    tmp = path.with_suffix(".tmp")
                    tmp.write_text(json.dumps(rows, separators=(",", ":")))
                    tmp.replace(path)
                    print(
                        case,
                        budget,
                        seed,
                        rep,
                        mode,
                        r["covered"],
                        r["stats"]["paid"],
                        flush=True,
                    )


if __name__ == "__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        run(args(), os.environ["TR_CASE"])
