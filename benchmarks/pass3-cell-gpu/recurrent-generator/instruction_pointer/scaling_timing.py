"""Counterbalanced single-threaded native timing after the training configuration is locked."""

import json
import time

import torch

from cell_kv_runtime import native
from continuous_stream import Stream
from continuous_trials import instrument, reference
from incremental_native import Ledger
from joint_cell_live import UniformDecoder
from partner_index_worlds import args
from scaling_archive import directory
from scaling_eval import Sampling, frozen
from scaling_fit import atomic


def run(a):
    d = directory(a)
    study = json.loads((d / "campaign.json").read_text())
    sel = study.get("locked")
    if not sel:
        return
    model = f"{sel['name']}-s113-t{sel['cap']}"
    out = d / "paired-native-timing.json"
    rows = json.loads(out.read_text()) if out.exists() else []
    done = {(r["rep"], r["method"], r["seed"]) for r in rows}
    methods = ("initial", "sweep", model, "factorized-random", "history")
    for rep in range(4):
        order = methods if rep % 2 == 0 else reversed(methods)
        for name in order:
            for seed in (193, 307):
                if (rep, name, seed) in done:
                    continue
                if time.time() >= study["end"] - 60:
                    return
                n, w, ref = frozen(
                    a, name if name in methods[:3] else "sweep", "sum-divisors"
                )
                if name == "history":
                    r = reference(a, "sum-divisors", ref, seed, 256)
                    response = None
                else:
                    instrument(n, "exact")
                    policy = (
                        Stream(UniformDecoder(), "A")
                        if name == "factorized-random"
                        else Sampling(n, 1.0, True)
                    )
                    trace = Ledger()
                    r = native(
                        a,
                        w,
                        policy=policy,
                        seed=seed,
                        slots=6,
                        submit_pages=2,
                        receipt_memory=True,
                        rule_state=True,
                        reference=ref,
                        execution_trace=trace,
                        paid_limit=256,
                    )
                    response = trace.response_digest
                paid = r["paid"] if name == "history" else r["stats"]["paid"]
                entry = {
                    "rep": rep,
                    "method": name,
                    "seed": seed,
                    "paid": paid,
                    "shortfall": 256 - paid,
                    "ops": r["ops"],
                    "ept": r["ops"] / paid if paid else 0.0,
                    "eps": r["eps"],
                    "wall": r["wall"],
                    "graph": r["graph"],
                    "response": response,
                    "facts": r["facts"],
                    "coverage": r["coverage"],
                    "covered": r["covered"],
                    "reference": r["reference"],
                }
                for prev in rows:
                    if prev["method"] == name and prev["seed"] == seed:
                        for key in ("paid", "ops", "graph", "response", "facts"):
                            if prev[key] != entry[key]:
                                raise ValueError(
                                    f"native timing replay changed {name}/{seed}/{key}"
                                )
                rows.append(entry)
                atomic(out, rows)


if __name__ == "__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        run(args())
