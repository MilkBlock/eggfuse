"""Offline native prefix differences. No replay evidence reaches the policy."""

import json
import os
from collections import defaultdict

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
            t = Trials(a, db, case, name, seed, True)
            row = {"model": name, "case": case, "seed": seed, "cap": 256}
            rows.append(row)
            try:
                trial = t.trial(256)
            except SourcePanic as error:
                row["error"] = str(error)
                continue
            requests = trial["requests"]
            owners = {r["owner"] for r in requests if r["complete"] and r["ops"]}
            effects = defaultdict(set)
            for i, r in enumerate(requests):
                if r["ops"] and r["owner"] in owners:
                    before = set(t.effect(requests[:i])["facts"])
                    after = set(t.effect(requests[: i + 1])["facts"])
                    effects[r["owner"]].update(("+", f) for f in after - before)
                    effects[r["owner"]].update(("-", f) for f in before - after)
            exact = t.effect(requests)
            assert all(exact[k] == trial["r"][k] for k in ("facts", "graph", "ops"))
            resolved = [
                frozenset(effects[o])
                for o in owners
                if any(sign == "+" for sign, _ in effects[o])
            ]
            row.update(
                productive=len(owners),
                distinct_visible_effects=len(set(resolved)),
                effect_signatures=json.dumps(
                    sorted({digest(sorted(effect)) for effect in resolved})
                ),
                unresolved=len(owners) - len(resolved),
            )
    table("effects-" + name.replace("/", "_") + ".csv", rows)


if __name__ == "__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        run(args(), os.environ["EXPOSURE_MODELS"])
