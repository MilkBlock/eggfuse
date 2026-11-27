"""Free native EggCC execution. Only unsigned generation changes between arms."""

import json
import os
from collections import Counter
from pathlib import Path

import torch

from cell_kv_runtime import native
from cell_kv_world import World
from competition_egg import egg
from foundation_egg_catalogue import install
from partner_index_worlds import args
from region_bake import linked
from trigger_execution import ExecutionTrace
from variable_completion import CompletionPolicy, directory, network


def run(a, case):
    d = directory(a)
    ir, reference = egg(a, case)
    units = linked(
        json.loads((ir / "program.json").read_text()),
        json.loads(
            (
                Path(os.environ["ARTIFACT_ROOT"]) / "region-owner-1126/menu.json"
            ).read_text()
        ),
    )
    arms = ["fixed_iid", "variable_iid", "variable_unique", "fixed_unique"]
    for seed in (71, 113):
        n = network(a, seed)
        n.actor.stop.load_state_dict(
            torch.load(d / f"boundary-{seed}.pt", weights_only=True)
        )
        w = World(ir, n.actor, entry_table=None, sides="")
        install(w, units, "multi")
        for budget in ("slots", "paid", "full"):
            for rep in (2, 3) if os.environ.get("SERIAL_TIMING") == "1" else (0, 1):
                for arm in arms if rep % 2 == 0 else reversed(arms):
                    path = d / f"{case}-{seed}-{budget}-{rep}-{arm}.json"
                    if path.exists():
                        continue
                    pol = CompletionPolicy(
                        n,
                        "unique" in arm,
                        384 if budget == "slots" else None,
                        arm.startswith("variable"),
                    )
                    audit = ExecutionTrace() if rep == 0 else None
                    r = native(
                        a,
                        w,
                        policy=pol,
                        receipt_log=pol,
                        receipt_memory=True,
                        slots=6,
                        submit_pages=2,
                        reference=reference,
                        paid_limit=96 if budget == "paid" else None,
                        seed=193,
                        rule_state=True,
                        execution_trace=audit,
                    )
                    r.update(
                        seed=seed,
                        arm=arm,
                        budget=budget,
                        case=case,
                        rep=rep,
                        count=pol.count,
                        decode=pol.decode_s,
                        prepare=pol.prepare_s,
                    )
                    if audit:
                        entries = list(audit.entries.values())
                        r["productive_requests"] = sum(
                            e["effective_ops"] > 0 for e in entries
                        )
                        r["different_productive_named"] = len(
                            {
                                (e["tid"], tuple(e["refs"]))
                                for e in entries
                                if e["effective_ops"]
                            }
                        )
                        r["arity"] = Counter(len(e["refs"]) for e in entries)
                        r["entries"] = entries
                    else:
                        prev = json.loads(
                            (d / f"{case}-{seed}-{budget}-0-{arm}.json").read_text()
                        )
                        assert all(
                            prev[k] == r[k] for k in ("graph", "facts", "stats", "ops")
                        )
                    tmp = path.with_suffix(".tmp")
                    tmp.write_text(json.dumps(r, separators=(",", ":")))
                    tmp.replace(path)
                    print(
                        case,
                        seed,
                        budget,
                        rep,
                        arm,
                        r["covered"],
                        r["stats"]["paid"],
                        flush=True,
                    )


if __name__ == "__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        run(args(), os.environ["TR_CASE"])
