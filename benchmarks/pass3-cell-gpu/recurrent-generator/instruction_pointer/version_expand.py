"""Offline extraction of additional named revision producers and execution with receipt guards."""

import argparse
import json
from collections import defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory

from boundary_inputs import CASE, folder, read
from entry_closure import named
from scaling_bake import save
from version_causes import Interventions
from version_replay import PRIOR, compile_dag, replay


def shrink(ids, test):
    """One-removal-minimal sufficient subset in this prefix. Never claim a global minimum."""
    ids = set(ids)
    if not test(ids):
        raise ValueError("full original seal did not publish the specified port")
    while True:
        before = len(ids)
        for t in sorted(ids):
            if test(ids - {t}):
                ids.remove(t)
        if before == len(ids):
            break
    return ids


def study(data, out):
    d = folder(data, CASE)
    tape = read(d / "tape.json")
    nodes = {q["token"]: q for q in tape["requests"]}
    frames = [json.loads(s) for s in (d / "memory.jsonl").open()]
    wires = compile_dag(nodes.values(), frames)
    publish = defaultdict(dict)
    for f in frames:
        for a, row in f["updates"]:
            publish[a["token"], a["op"]].setdefault(row["version"], f["run"])
    witnesses = {
        w["root"]: set(w["chain"]) for w in read(PRIOR / "dependency.json")["witnesses"]
    }
    cached = {}
    original = read(out / "causes.json")["rows"]
    singles = {
        (tuple(r["address"]), r["version"]): r["sufficient_single_requests"]
        for r in original
    }
    with TemporaryDirectory() as tmp:
        probes = Interventions(data, Path(tmp))
        for row in read(PRIOR / "boundaries.json"):
            if row["label"] != "both_ancestries":
                continue
            initial = set(row["region"]["tokens"])
            seen = set()
            stack = list(initial)
            causes = {}
            while stack:
                k = stack.pop()
                if k in seen:
                    continue
                seen.add(k)
                for i, p in enumerate(nodes[k]["parents"]):
                    t, op, v = named(p)
                    if t > 0:
                        stack.append(t)
                    if wires[k][i][2] == 1:
                        continue
                    a = t, op
                    if (a, v) not in cached:
                        run = publish[a][v] - 1
                        full = {q["token"] for q in probes.by[run]}
                        answer = probes.observation(run, full)[a]

                        def matches(subset):
                            return probes.observation(run, subset).get(a) == answer

                        candidates = singles.get((a, v), [])
                        chosen = (
                            {candidates[0]} if candidates else shrink(full, matches)
                        )
                        if not matches(chosen) or not chosen:
                            raise ValueError(
                                ("unsupported exogenous publication", a, v, run)
                            )
                        cached[a, v] = chosen
                    causes[k, i] = cached[a, v]
                    stack.extend(causes[k, i])
            group = [nodes[k] for k in sorted(seen)]
            precedes = defaultdict(set)
            for (k, i), writers in causes.items():
                src, pc, _ = named(nodes[k]["parents"][i])
                if src > 0:
                    for writer in writers:
                        if nodes[src]["run"] < nodes[writer]["run"]:
                            precedes[writer].add(src)
            res = []
            for mode in ("region_order", "ordinal", "causal", "ordered_causes"):
                result = replay(
                    data,
                    tape,
                    group,
                    wires,
                    mode,
                    causes=causes,
                    precedes=precedes if mode == "ordered_causes" else None,
                )
                result["target_accepted"] = sum(
                    result["issued"].get(k, [0, None])[1] == "accepted" for k in initial
                )
                result["target_total"] = len(initial)
                result["eight_accepted"] = sum(
                    result["issued"].get(k, [0, None])[1] == "accepted"
                    for k in witnesses[row["root"]]
                )
                res.append(result)
            save(
                out / f"expanded-{row['root']}.json",
                dict(
                    root=row["root"],
                    added=sorted(seen - initial),
                    writer_after_owner={k: sorted(v) for k, v in precedes.items()},
                    revision_edges=[
                        [k, i, sorted(c)] for (k, i), c in sorted(causes.items())
                    ],
                    results=res,
                ),
            )
            print(
                row["root"],
                len(seen),
                [(r["mode"], r["target_accepted"], r["eight_accepted"]) for r in res],
                flush=True,
            )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("out", type=Path)
    a = p.parse_args()
    study(a.root, a.out)
