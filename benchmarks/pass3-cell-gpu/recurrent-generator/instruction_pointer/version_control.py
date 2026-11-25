"""Check an order-preserving publication DAG with no archived Run numbers at dispatch.
Its conservative barriers are an offline positive control and include work outside each slice.
"""

import argparse
import json
from itertools import groupby
from pathlib import Path

from boundary_inputs import CASE, folder, read
from scaling_bake import save
from version_replay import PRIOR, compile_dag, replay


def study(data, out):
    d = folder(data, CASE)
    tape = read(d / "tape.json")
    nodes = tape["requests"]
    groups = [
        [q["token"] for q in group]
        for _, group in groupby(nodes, key=lambda q: q["run"])
    ]
    with (d / "memory.jsonl").open() as f:
        wires = compile_dag(nodes, map(json.loads, f))
    result = replay(data, tape, nodes, wires, "full_groups", groups=groups)
    issued = result.pop("issued")
    boundaries = [
        r for r in read(PRIOR / "boundaries.json") if r["label"] == "both_ancestries"
    ]
    result["regions"] = {
        r["root"]: sum(
            issued.get(k, [0, ""])[1] == "accepted" for k in r["region"]["tokens"]
        )
        for r in boundaries
    }
    result["nonempty_groups"] = len(groups)
    save(out / "control-dag.json", result)
    print(result, flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("data", type=Path)
    p.add_argument("out", type=Path)
    a = p.parse_args()
    study(a.data, a.out)
