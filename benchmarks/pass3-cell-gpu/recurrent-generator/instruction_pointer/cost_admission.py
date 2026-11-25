"""Charge the observed search saving against an isolated index build per donor entry."""

import argparse
from pathlib import Path

import numpy as np

from cost_catalog import prepare
from protocol_experiment import dump
from recursive_train import folder, read
from ripsat_layout import signatures


def admit(data, store):
    case = "sum"
    ids = prepare(data, store, case)
    p = read(folder(data, case) / "program.json")
    sig = signatures(p)
    a, b = [np.load(store / f"sum{x}-ledger.npz") for x in ("", "-single")]
    if not np.array_equal(a["meta"], b["meta"]) or not np.array_equal(
        a["verdict"][:, :-2], b["verdict"][:, :-2]
    ):
        raise ValueError("donor counterfactual changed a publication or proof verdict")
    old, new = a["depth"][:, :, 1].sum(1), b["depth"][:, :, 1].sum(1)
    rows = []
    import json
    import subprocess
    from collections import Counter

    from recursive_train import binary

    d = folder(data, case)
    # Reconstruct the model's own publication-time table sizes from native replay.
    memory = store / "sum-native-memory.jsonl"
    subprocess.run(
        [binary(data), "replay", d / "program.json", store / "sum-issued.json", "audit", "--memory", memory],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    names = {t["name"]: i for i, t in enumerate(p["recipe"]["tables"])}
    active = {}
    counts = Counter()
    byrun = {}
    for i in ids:
        byrun.setdefault(int(a["meta"][i, 0]), []).append(i)
    for line in memory.open():
        frame = json.loads(line)
        for x in frame["retired"]:
            addr = x["token"], x["op"]
            counts[active.pop(addr)] -= 1
        for x, row in frame["updates"]:
            addr = x["token"], x["op"]
            if addr not in active:
                active[addr] = row["table"]
                counts[row["table"]] += 1
        for i in byrun.get(frame["run"], ()):
            run, r, j = a["meta"][i, :3]
            tabs = {names[v["table"]] for v in p["recipe"]["rules"][r]["interface"]["rows"]}
            # Only one cut-depth index per root. Bound even an unshared build
            # by the largest involved table, plus one root choice.
            tax = 1 + max(counts[t] for t in tabs)
            saved = int(old[i] - new[i])
            rows.append(
                {
                    "entry": [sig[r], int(j)],
                    "rule": int(r),
                    "run": int(run),
                    "event": int(i),
                    "before": int(old[i]),
                    "after": int(new[i]),
                    "index_and_choice_bound": tax,
                    "admit": saved > tax,
                }
            )
    if len(rows) != len(ids):
        raise ValueError("missing single-region measurement")
    dump(store / "sum-local-admission.json", rows)
    dump(store / "cost-book.json", {"training": "sum", "entries": [x["entry"] for x in rows if x["admit"]]})


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("data", type=Path)
    p.add_argument("store", type=Path)
    a = p.parse_args()
    admit(a.data, a.store)
