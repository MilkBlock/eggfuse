"""Positive/negative controls further upstream on the learner's native prefix."""

import argparse
from pathlib import Path

from boundary_inputs import BASE, CASE, binary, folder, frozen_tape, read
from boundary_native import run_graph
from boundary_region import region
from boundary_study import snapshots
from entry_closure import Tape, named
from region_bake import linked
from scaling_bake import save


def controls(root, out):
    d = folder(root, CASE)
    exe = binary(root)
    t = Tape(d, exe)
    model = frozen_tape()["tape"]
    deps = read(out / "dependency.json")
    ex = read(out / "exact.json")
    primary = deps["witnesses"][0]
    ancestors = set(primary["right"])
    # Extract the actual r575 chain ending at the TypeList-length read by r49.
    leaf = named(t.q[primary["args"][1][0]]["parents"][2])[0]
    chain = []
    while t.q[leaf]["rule"] == 575:
        chain.append(leaf)
        following = [
            named(p)[0]
            for p in t.q[leaf]["parents"]
            if named(p)[0] in t.q and t.q[named(p)[0]]["rule"] in (574, 575)
        ]
        if len(following) != 1:
            raise ValueError("ambiguous producer chain")
        leaf = following[0]
    chain.reverse()
    r = region(t, chain, set())
    # Root 574 has zero inputs on this program. Prove its corresponding receipt in the model.
    tm = t.q[leaf]
    candidates = [
        q
        for q in model["requests"]
        if q["rule"] == tm["rule"] and q["parents"] == tm["parents"] and q["run"] == tm["run"]
    ]
    if len(candidates) != 1:
        raise ValueError("missing known base receipt")
    root_run = r["runs"][0]
    ext = [(candidates[0]["token"] if k == leaf else k, pc, v) for k, pc, v in r["external"]]
    assert all(k in (1, leaf) for k, _, _ in r["external"])
    chain_trial = run_graph(exe, d, out, model["requests"], root_run, r["unit"], ext)
    menu = linked(t.program, read(BASE / "menu.json"))
    viable = {}
    for rid, u in menu.items():
        occ = [v for v in t.occasions(u) if ancestors.intersection(v)]
        if occ:
            viable[rid] = dict(
                unit=u,
                witnesses=occ,
                successful_teacher_producers=sorted(set().union(*(ancestors.intersection(v) for v in occ))),
                own=[],
            )
    for run, qs in ex.items():
        for q in qs:
            if q["rule"] not in viable:
                continue
            v = viable[q["rule"]]
            u = v["unit"]
            refs = list(map(named, q["parents"]))
            v["own"].append(
                dict(
                    run=int(run),
                    refs=refs,
                    trial=run_graph(exe, d, out, model["requests"], int(run), u, refs),
                )
            )
    actual = next(q for q in model["requests"] if q["run"] == root_run and q["rule"] == 575)
    for f, live in snapshots(out / "model-memory.jsonl"):
        if f["run"] == root_run:

            def values(q):
                return [live[named(p)[:2]]["hashes"] for p in q["parents"]]

            checks = dict(
                signed=actual,
                chosen_fields=values(actual),
                target_fields=[live[(k, pc)]["hashes"] for k, pc, v in (ext[i] for _, i in r["unit"][0][2])],
                legal=[
                    dict(parents=q["parents"], fields=values(q))
                    for q in ex[str(root_run)]
                    if q["rule"] == 575
                ],
            )
            break
    save(
        out / "upstream.json",
        dict(
            chain=chain,
            base=leaf,
            external=ext,
            chain_trial=chain_trial,
            root_comparison=checks,
            catalog=viable,
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("out", type=Path)
    a = p.parse_args()
    controls(a.root, a.out)
