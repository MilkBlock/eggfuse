"""Evaluate each batched checkpoint on native paid requests at a fixed cap."""

import csv
import os
import sys
import torch
from partner_index_worlds import args
from exposure_eval import Database, Trials, SourcePanic
from exposure_train import output
from exposure_worlds import HELD


def run(a):
    torch.set_num_threads(1)
    db = Database(output(a) / "native.sqlite")
    name = os.environ["EXPOSURE_MODELS"]
    fields = (
        "model",
        "program",
        "seed",
        "paid",
        "covered",
        "reference",
        "ops",
        "coverage",
        "ept",
        "eps",
        "graph",
        "error",
    )
    writer = csv.DictWriter(sys.stdout, fields)
    writer.writeheader()
    with torch.no_grad():
        for case in ("fact", "loopfact", "sum-divisors", *HELD):
            for seed in (193, 307):
                t = Trials(a, db, case, name, seed, True)
                row = dict(model=name, program=case, seed=seed)
                try:
                    trial = t.trial(256)
                    r = trial["r"]
                    row.update(
                        {
                            k: r[k]
                            for k in fields
                            if k
                            in (
                                "covered",
                                "reference",
                                "ops",
                                "coverage",
                                "ept",
                                "eps",
                                "graph",
                            )
                        }
                    )
                    row.update(paid=len(trial["requests"]))
                except SourcePanic as exc:
                    row["error"] = str(exc)
                writer.writerow(row)
                sys.stdout.flush()


if __name__ == "__main__":
    run(args())
