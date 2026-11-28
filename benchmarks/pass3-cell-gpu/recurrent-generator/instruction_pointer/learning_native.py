"""Native outcomes; count complete productive names separately from duplicate receipts."""

import os

import torch

from exposure_eval import Database, SourcePanic, Trials
from exposure_train import output
from exposure_worlds import HELD
from int_parameters import digest
from learning_entropy import table
from partner_index_worlds import args


def run(a, name):
    db = Database(output(a) / "native.sqlite")
    rows = []
    for case in ("sum-divisors", "fact", "loopfact", *HELD):
        for seed in (193, 307):
            target = Trials(a, db, case, name, seed, True)
            base = Trials(a, db, case, "local-s71-t100000", seed, True)
            for cap in (256, None):
                row = {
                    "model": name,
                    "case": case,
                    "seed": seed,
                    "cap": cap or "schedule",
                }
                try:
                    trial = target.trial(cap)
                    initial = base.trial(cap)
                except SourcePanic as e:
                    rows.append(dict(row, error=str(e)))
                    continue
                r = trial["r"]
                events = trial["requests"]
                positive = {
                    digest(x["name"]) for x in events if x["complete"] and x["ops"] > 0
                }
                facts = set(r["facts"])
                old = set(initial["r"]["facts"])
                n = len(events)
                dup = r["receipts"].get("duplicates", 0)
                completed = [x for x in events if x["owner"] == x["reply"][0]]
                row.update(
                    paid=n,
                    covered=len(facts),
                    reference=r["reference"],
                    coverage=r["coverage"],
                    ops=r["ops"],
                    ept=r["ept"],
                    eps=r["eps"],
                    wall=r["wall"],
                    productive_names=len(positive),
                    native_dups=dup,
                    duplicate_rate=dup / n if n else None,
                    name_reissues=len(completed)
                    - len({digest(x["name"]) for x in completed}),
                    receipts_rejected=str(r["receipts"].get("rejected", {})),
                    graph=r["graph"],
                    same_graph_100k=r["graph"] == initial["r"]["graph"],
                    facts_only_new=str(sorted(facts - old)),
                    facts_only_100k=str(sorted(old - facts)),
                )
                rows.append(row)
    table("native-" + name.replace("/", "_") + ".csv", rows)


if __name__ == "__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        run(args(), os.environ["EXPOSURE_MODELS"])
