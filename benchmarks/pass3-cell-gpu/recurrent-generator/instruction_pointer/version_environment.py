"""How much observed environment must accompany the ten overlapping regions?
The prefix cutoff is an offline construction parameter. Dispatch uses only real publications.
"""

import argparse
import json
from collections import defaultdict
from itertools import groupby
from pathlib import Path

from boundary_inputs import CASE, folder, read
from scaling_bake import save
from version_replay import PRIOR, compile_dag, replay


def study(data, out):
    d = folder(data, CASE)
    tape = read(d / "tape.json")
    nodes = tape["requests"]
    witnesses = read(PRIOR / "dependency.json")["witnesses"]
    cases = {w["root"]: set(w["chain"] + w["left"] + w["right"]) for w in witnesses}
    goals = {w["root"]: set(w["chain"]) for w in witnesses}
    region = set.union(*cases.values())
    target = set.union(*goals.values())
    gold = defaultdict(dict)
    frames = [json.loads(s) for s in (d / "memory.jsonl").open()]
    for f in frames:
        ids = {q["token"] for q in f["accepted"]} & target
        for a, r in f["updates"]:
            if a["token"] in ids:
                gold[a["token"]][a["op"]] = [
                    r["table"],
                    r["version"],
                    int(r["forwarded"]),
                    r["hashes"],
                ]
    wires = compile_dag(nodes, frames)
    rows = []
    for cutoff in (0, 17, 26, 53, 99, 119, 151):
        group = [q for q in nodes if q["run"] <= cutoff or q["token"] in region]
        batches = [
            [q["token"] for q in batch]
            for _, batch in groupby(group, key=lambda q: q["run"])
        ]
        r = replay(
            data, tape, group, wires, "group_barrier", groups=batches, observed=target
        )
        r["cutoff"] = cutoff
        r["outside"] = len(group) - len(region)
        published = r.pop("first_returns")

        def good(k):
            return (
                r["issued"].get(k, [0, None])[1] == "accepted"
                and published.get(k, {}) == gold[k]
            )

        def content(ports):
            return {
                pc: (tab, fwd, values) for pc, (tab, ver, fwd, values) in ports.items()
            }

        r["named_contents_complete"] = [
            k
            for k, c in goals.items()
            if all(
                r["issued"].get(t, [0, None])[1] == "accepted"
                and content(published.get(t, {})) == content(gold[t])
                for t in c
            )
        ]
        r["examples"] = []
        for t in sorted(target):
            if r["issued"].get(t, [0, None])[1] == "accepted" and not good(t):
                r["examples"].append(
                    dict(token=t, expected=gold[t], received=published.get(t, {}))
                )
                break
        r["closures_complete"] = [
            k
            for k, c in cases.items()
            if all(r["issued"].get(t, [0, None])[1] == "accepted" for t in c)
        ]
        r["target_semantic_complete"] = [
            k for k, c in goals.items() if all(good(t) for t in c)
        ]
        r["verified_target_nodes"] = sum(map(good, target))
        r.pop("blocking_wires")
        r.pop("issued")
        rows.append(r)
    save(out / "environment.json", rows)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("data", type=Path)
    p.add_argument("out", type=Path)
    a = p.parse_args()
    study(a.data, a.out)
