"""Independent CPU AB/BA timings. Verify full named trajectories against stored native runs."""

from pathlib import Path
from tempfile import TemporaryDirectory

import torch

from exposure_eval import Database, SourcePanic, Trials
from exposure_train import output
from exposure_worlds import HELD
from learning_entropy import table
from partner_index_worlds import args


def run(a):
    original = Database(output(a) / "native.sqlite")
    local = "A-batched/local-s71-t1000000"
    full = "matched-end-to-end/full-s71-t1000000"
    rows = []
    with TemporaryDirectory() as scratch:
        for case in ("sum-divisors", "fact", "loopfact", *HELD):
            for seed in (193, 307):
                for order, name in enumerate((local, full, full, local)):
                    independent = Database(Path(scratch) / f"{order}.sqlite")
                    t = Trials(a, independent, case, name, seed, True)
                    try:
                        expected = Trials(a, original, case, name, seed, True).trial(
                            256
                        )
                    except SourcePanic as failed:
                        rows.append(
                            {
                                "case": case,
                                "seed": seed,
                                "model": name,
                                "order": order,
                                "error": str(failed),
                            }
                        )
                        continue
                    actual = t.trial(256)
                    assert actual["requests"] == expected["requests"]
                    r = actual["r"]
                    assert all(
                        r[k] == expected["r"][k]
                        for k in ("graph", "facts", "ops", "receipts")
                    )
                    rows.append(
                        {
                            "case": case,
                            "seed": seed,
                            "model": name,
                            "order": order,
                            "paid": len(actual["requests"]),
                            "ops": r["ops"],
                            "coverage": r["coverage"],
                            "graph": r["graph"],
                            "wall": r["wall"],
                            "eps": r["eps"],
                        }
                    )
    table("timing-abba.csv", rows)


if __name__ == "__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        run(args())
