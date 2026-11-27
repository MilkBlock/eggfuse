"""Held-out complete-Token likelihood and paid-budget autonomous trajectories at successive exposures."""

import json
import os
from time import perf_counter, sleep

import torch

from cell_kv_world import World
from competition_egg import egg
from incremental_fit import output
from incremental_native import run_one
from joint_cell_corpus import folder, read_rows
from joint_cell_sweep import complete_ce
from joint_cell_train import fitted
from partner_index_worlds import args


def run(a, case):
    out = output(a)
    n = fitted(a, case, "sweep", 0)
    w = World(egg(a, case)[0], n.actor, entry_table=None, sides="")
    data = {
        source: read_rows(folder(a) / f"{case}-{source}.pkl.gz")
        for source in ("teacher", "autonomous")
    }
    pending = ["initial"] + [
        f"{arm}-{seed}-e{epoch}"
        for seed in (71, 113)
        for epoch in (1, 2, 3)
        for arm in ("A", "B", "C")
    ]
    cutoff = perf_counter() + 3600
    while pending:
        for model in pending.copy():
            dest = out / f"eval-{case}-{model}.json"
            if dest.exists():
                pending.remove(model)
                continue
            name = None if model == "initial" else f"{case}-{model}"
            if name and not (out / (name + ".pt")).exists():
                continue
            n = fitted(a, case, "sweep", 0)
            if name:
                n.load_state_dict(torch.load(out / (name + ".pt"), weights_only=True))
            n.grouped_training_reduction = True
            n.prepare(w)
            held = {}
            for src, rows in data.items():
                loss = targets = states = 0
                for s, ts in rows:
                    if ts:
                        loss += float(complete_ce(n, w, n.state(w, s), ts)) * len(ts)
                        targets += len(ts)
                        states += 1
                held[src] = {
                    "states": states,
                    "targets": targets,
                    "ce": loss / targets if targets else None,
                }
            # Use the same initial weights for zero-exposure autonomous trials.
            if not name:
                name = f"{case}-init"
                torch.save(n.state_dict(), out / (name + ".pt"))
            results = [
                run_one(a, case, "cache", draw, cap, name)
                for draw in (193, 307)
                for cap in (64, 256)
            ]
            dest.write_text(
                json.dumps(
                    {"case": case, "model": model, "heldout": held, "runs": results}
                )
            )
            pending.remove(model)
            print(dest.name, flush=True)
        if pending:
            if perf_counter() > cutoff:
                raise TimeoutError(pending)
            sleep(2)


if __name__ == "__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        run(args(), os.environ["TR_CASE"])
