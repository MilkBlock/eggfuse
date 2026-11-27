"""Measure physical CPU batch capacity at six unchanged generation slots per native Run."""

import json
import os
import time

import torch

from incremental_batch import trial
from incremental_native import run_one
from partner_index_worlds import args
from scaling_archive import directory
from scaling_eval import frozen
from scaling_fit import atomic


def run(a):
    d = directory(a)
    st = json.loads((d / "campaign.json").read_text())
    chosen = st["locked"]
    model = os.getenv("CELL_MODEL")
    if not model:
        if not chosen:
            return
        model = f"{chosen['name']}-s113-t{chosen['cap']}"
    if model != "sweep" and (
        not chosen or model != f"{chosen['name']}-s113-t{chosen['cap']}"
    ):
        raise ValueError(
            "batch benchmark expects frozen baseline or preselected policy"
        )

    def setup(aa, case):
        return frozen(aa, model, case)

    def signature(r):
        return (
            r["native_digest"],
            r["origins_digest"],
            r["graph"],
            r["facts"],
            r["ops"],
            r["stats"]["paid"],
        )

    out = d / f"packed-{model}.json"
    rows = json.loads(out.read_text()) if out.exists() else []
    if len(rows) == 6:
        return
    case = "loopfact"
    seeds = (193, 307, 411, 509)
    controls = [run_one(a, case, "cache", s, 128, setup_world=setup) for s in seeds]
    os.environ["IK_BATCH_KV"] = "1"
    for rep, order in enumerate(((1, 2, 4), (4, 2, 1))):
        for cap in order:
            if any(r["rep"] == rep and r["capacity"] == cap for r in rows):
                continue
            if time.time() >= st["end"] - 90:
                return
            row = trial(a, case, "cpu", cap, 128, setup_world=setup)
            matched = [
                signature(x) == signature(y)
                for x, y in zip(controls, row["runs"], strict=True)
            ]
            rows.append(
                dict(
                    row,
                    model=model,
                    rep=rep,
                    matched=matched,
                    control_sha=[r["native_digest"] for r in controls],
                )
            )
            atomic(out, rows)
            if not all(matched):
                return


if __name__ == "__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        run(args())
