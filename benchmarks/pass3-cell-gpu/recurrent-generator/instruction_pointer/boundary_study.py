"""Held-case-only Bake boundary diagnosis. All proof enumeration and interventions stay offline."""

import argparse
import json
from collections import Counter, defaultdict
from itertools import product
from pathlib import Path
from tempfile import TemporaryDirectory

from boundary_inputs import BASE, CASE, collect, frozen_tape
from boundary_native import run_graph
from boundary_region import ancestors, cuts, region
from entry_closure import Tape, named
from receipt_takeover import replay_many
from recursive_train import binary, folder, read
from region_bake import linked
from scaling_bake import save


def snapshots(path):
    live = {}
    for line in path.open():
        f = json.loads(line)
        for a in f["retired"]:
            live.pop((a["token"], a["op"]), None)
        for a, row in f["updates"]:
            live[a["token"], a["op"]] = row
        yield f, live


def first_group(r):
    return [(rid, w) for rid, g, w in r["unit"] if g == 0]


def entry_probe(r, frame, live, proofs, model, t, out, cache, exe):
    """Negative only on necessary conditions. Prefer the known initialization evidence.
    Exact-native positive plus a concrete certificate suffices for existential admission.
    An unsuccessful trial without an impossibility proof remains unknown."""
    group = first_group(r)
    run = frame["run"]
    by = defaultdict(list)
    for q in proofs:
        by[q["rule"]].append(q)
    rr = Counter(rid for rid, _ in group)
    for rid, count in rr.items():
        if len(by[rid]) < count:
            return dict(status="no", reason="insufficient_native_group_bindings", rule=rid)
    bytype = defaultdict(list)
    for addr, row in live.items():
        bytype[row["table"]].append((*addr, row["version"]))
    ext = [None] * len(r["external"])
    for i, (ref, tab) in enumerate(zip(r["external"], r["types"], strict=True)):
        if not bytype[tab]:
            return dict(status="no", reason="no_visible_typed_port", slot=i, table=tab)
        # These snapshots share the exact initial program and a checked Run-1
        # initialization. Other teacher IDs never address the independent fork.
        if ref[0] <= 1 and ref in bytype[tab]:
            ext[i] = ref
        else:
            ext[i] = min(bytype[tab])
    bound = {}
    used = set()
    # Concrete named positive witness only; canonical alternative owners may differ.
    for rid, w in group:
        for q in by[rid]:
            if q["token"] in used:
                continue
            next_bound = dict(bound)
            if all(
                next_bound.setdefault(slot, named(p)) == named(p)
                for (_, slot), p in zip(w, q["parents"], strict=True)
            ):
                used.add(q["token"])
                bound = next_bound
                break
        else:
            return dict(status="unknown", reason="canonical_named_group_conflict")
    for i, v in bound.items():
        ext[i] = v
    key = (run, json.dumps(r["unit"]), tuple(ext))
    if key not in cache:
        cache[key] = run_graph(exe, t.folder, out, model["requests"], run, r["unit"], ext)
    result = cache[key]
    return dict(status="yes" if result["entry"] else "unknown", trial=result, refs=ext)


def typed_join49(t, live):
    # Rule 49 in this precise program has only three table atoms. Compare
    # intra-snapshot fingerprints, then validate opportunity counts natively.
    query = t.program["recipe"]["rules"][49]["query"]
    expected = [("TupleT", [0, 1]), ("HasType", [2, 1, 3]), ("TypeList-length", [0, 4])]
    assert [(a["call"]["table"], [v["slot"] for v in a["args"]]) for a in query] == expected
    tabs = t.rules.inputs[49]
    x, y, z = [{tuple(r["hashes"]) for r in live.values() if r["table"] == tab} for tab in tabs]
    return dict(
        distinct_rows=[len(x), len(y), len(z)],
        tuple_has_type=sum(a[1] == b[1] for a, b in product(x, y)),
        tuple_length=sum(a[0] == c[0] for a, c in product(x, z)),
        all_equalities=sum(a[1] == b[1] and a[0] == c[0] for a, b, c in product(x, y, z)),
    )


def study(root, out):
    d = folder(root, CASE)
    exe = binary(root)
    t = Tape(d, exe)
    m = linked(t.program, read(BASE / "menu.json"))
    chains = t.occasions(m[56])
    saved = frozen_tape()
    if not (t.q[1]["rule"] == 375 and saved["tape"]["requests"][0] == t.q[1] and not t.q[1]["parents"]):
        raise ValueError("common initializer identity unavailable")
    model = saved["tape"]
    exact = read(out / "exact.json")
    teach_credit = dict(read(out / "teacher-credit.json")["origins"])
    witnesses = []
    rows = []
    all_nodes = set()
    repairs = {e["token"]: e for e in read(d / "tape.json")["repair_events"]}
    teacher_ref = read(d / "capture.json")
    for chain in chains:
        k = chain[0]
        args = list(map(named, t.q[k]["parents"]))
        a, b = [ancestors(t.q, p[0]) for p in args]
        all_nodes.update(a | b | set(chain))
        witnesses.append(
            dict(root=k, chain=chain, args=args, left=sorted(a), right=sorted(b), shared=sorted(a & b))
        )
        for label, absorbed in cuts(t, chain).items():
            r = region(t, chain, absorbed)
            if any(p[2] in ("undeclared_output", "unsealed") for p in r["problems"]):
                raise ValueError("invalid layout for native verifier")
            r["teacher_only"] = run_graph(exe, d, out, t.tape, r["runs"][0], r["unit"], r["external"])
            r["tape_effective"] = sum(teach_credit[tok] for tok in r["tokens"])
            # Exact-versioned full-run replacement; keep other signed teacher
            # operations and compare final state, schedule, writes and events.
            if not r["late"] and not r["problems"]:
                with TemporaryDirectory(dir=out) as tmp:
                    path = Path(tmp) / "layout.json"
                    save(path, [r["unit"]])
                    try:
                        r["takeover"] = replay_many(d, exe, path, [(0, r["tokens"])], t.tape, teacher_ref)
                    except ValueError as err:
                        r["takeover"] = dict(error=str(err)[:700])
            rows.append(dict(root=k, label=label, region=r, own=[]))
        print("teacher witness", k, flush=True)
    cache = {}
    operands = []
    snapshots_by_rule = defaultdict(list)
    schedule = dict(saved["schedule"])
    for frame, live in snapshots(out / "model-memory.jsonl"):
        run = frame["run"]
        scheduled = dict(frame["rules"])
        proofs = exact.get(str(run), [])
        if sorted(scheduled) != sorted(schedule.get(run, ())):
            raise ValueError("native and frozen schedule differ")
        for rid in scheduled:
            snapshots_by_rule[rid].append((run, [q for q in proofs if q["rule"] == rid]))
        if 49 in scheduled:
            operands.append(dict(run=run, **typed_join49(t, live)))
        for row in rows:
            r = row["region"]
            if all(rid in scheduled for rid, w in first_group(r)):
                row["own"].append(
                    dict(run=run, **entry_probe(r, frame, live, proofs, model, t, out, cache, exe))
                )
    model_counts = Counter(q["rule"] for q in model["requests"])
    roles = {}
    rules = {t.q[k]["rule"] for k in all_nodes}
    for rid in sorted(rules):
        v = snapshots_by_rule[rid]
        roles[rid] = dict(
            rule=t.program["recipe"]["rules"][rid]["metadata"]["name"],
            accepted=model_counts[rid],
            exact_next=sum(len(p) for _, p in v),
            scheduled_runs=len(v),
            productive_runs=[run for run, p in v if p],
            catalog_producers=[(r, i, len(u)) for r, u in m.items() for i, s in enumerate(u) if s[0] == rid],
        )
    ext = {named(p)[0] for k in all_nodes for p in t.q[k]["parents"]} - all_nodes
    first_frame = next(snapshots(d / "memory.jsonl"))[1]
    if not all(k in repairs or any(a[0] == k for a in first_frame) for k in ext):
        raise ValueError("unclassified external producer")
    stats = dict(
        credit={k: teach_credit[k] for k in all_nodes},
        queries={r: t.program["recipe"]["rules"][r]["query"] for r in rules},
        witnesses=witnesses,
        nodes=[t.q[k] for k in sorted(all_nodes)],
        boundary_owners={k: repairs.get(k, "initial") for k in sorted(ext)},
        rules=roles,
        rule49_inputs=operands,
        source_sha=t.program["recipe"]["sha256"],
    )
    save(out / "dependency.json", stats)
    save(out / "boundaries.json", rows)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--reuse-exact", action="store_true")
    a = p.parse_args()
    a.out.mkdir(exist_ok=True, parents=True)
    if not a.reuse_exact:
        collect(a.root, a.out)
    study(a.root, a.out)
