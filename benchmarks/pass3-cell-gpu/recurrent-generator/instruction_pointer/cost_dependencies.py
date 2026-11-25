"""Native proof provenance and strict uniqueness ceilings on the costly event sets."""

import argparse
import gzip
import json
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from entry_closure import named
from entry_marginal import path_costs
from evidence_regions import HORIZON, INPUT, OUTPUT, entry_events, grow
from protocol_experiment import dump
from receipt_bake import Snapshot
from recursive_train import folder, read
from ripsat_layout import signatures


def slot_set(args):
    return {a["slot"] for a in args if "slot" in a}


def dependencies(rule, j):
    rows = rule["interface"]["rows"]
    known = slot_set(rows[j]["columns"])
    needed = {i for i, s in enumerate(rule["slots"]) if s["definition"] == "query"}
    # FD gives at most one successful row. It supplies no evidence of existence.
    primitives = set()
    while True:
        old = len(known)
        for row in rows:
            cols = row["columns"]
            if slot_set(cols[k] for k in row["key_columns"]) <= known:
                known.update(slot_set(cols))
        for atom in rule["query"]:
            args = atom["args"]
            if "primitive" in atom["call"] and args and slot_set(args[:-1]) <= known:
                known.update(slot_set(args[-1:]))
                primitives.update(slot_set(args[-1:]))
        if old == len(known):
            break
    return needed <= known, len(primitives)


def compiled_outputs(case, data, store, program, q, tape):
    import subprocess
    from tempfile import TemporaryDirectory

    from entry_closure import Rules
    from recursive_train import binary

    contract = json.loads(
        subprocess.check_output([binary(data), "receipt-contract", folder(data, case) / "program.json"])
    )
    if contract["recipe_sha256"] != program["recipe"]["sha256"]:
        raise ValueError("Recipe mismatch")
    book = read(store / "evidence-book.json")
    frozen = {
        (tuple(s), tuple((r, tuple(map(tuple, w))) for r, w in plan)): pid
        for pid, (s, plan) in enumerate(book["regions"])
    }
    launches = []
    stamps = {}
    maps = defaultdict(set)
    with TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "memory.jsonl").symlink_to(store / f"{case}-native-memory.jsonl")
        times = defaultdict(list)
        init = {}
        (tmp / "tape.json").symlink_to(store / f"{case}-issued.json")
        (tmp / "program.json").symlink_to(folder(data, case) / "program.json")
        for line in (tmp / "memory.jsonl").open():
            f = json.loads(line)
            for r, _ in f["rules"]:
                times[r].append(f["run"])
            for a, row in f["updates"]:
                stamps[a["token"], a["op"], row["version"]] = (row["table"], tuple(row["hashes"]))
                if a["token"] < 0 and a["token"] % 2:
                    init[a["token"], a["op"]] = row["table"]
        uses = defaultdict(list)
        for req in q.values():
            for src in {named(x)[0] for x in req["parents"]}:
                uses[src].append((req["run"], req["token"]))
        t = SimpleNamespace(
            folder=tmp, program=program, q=q, rules=Rules(contract), schedule=times, snap=Snapshot(tmp)
        )
        e = SimpleNamespace(t=t, uses=uses, sigs=signatures(program), initial_tables=init)
        for run, tok, source, outs, ins in entry_events(e):
            known = {p: (INPUT, i) for i, p in enumerate(ins) if t.snap.version(*p[:2], run) == p[2]}
            known.update({p: (OUTPUT, pc) for pc, p in outs.items()})
            direct = [x for x in uses[tok] if run <= x[0] <= run + HORIZON]
            extras = set()
            for rs, k in direct:
                if rs == run:
                    missing = [p for p in map(named, q[k]["parents"]) if p not in known]
                    if len(missing) == 1 and t.snap.version(*missing[0][:2], run) == missing[0][2]:
                        extras.add(missing[0])
            for other in [None, *extras]:
                plan, ts = grow(e, run, tok, known, direct, other)
                if (source, plan) in frozen:
                    pc = min(outs)
                    launches.append(
                        (run, tok, pc, outs[pc][2], stamps[outs[pc]], frozen[source, plan], other, ts)
                    )
                    for v in ts:
                        for pc in t.rules.rules[q[v]["rule"]]["outputs"]:
                            ver = t.snap.version(v, int(pc), q[v]["run"] + 1)
                            if ver is not None:
                                maps[tok, other].add((v, int(pc), ver))
        costs = path_costs(data, tmp, {t for *_, ts in launches for t in ts}) if launches else {}
        selected = []
        occupied = set()
        events = set()
        order = []
        for row in launches:
            counts = sum((costs[t] for t in row[-1]), Counter())
            net = (
                counts["removed_terminal_visits"]
                + counts["unary_event_skips"]
                + counts["suppressed_b_proposals"]
                - len(row[-1])
                - 1
                - int(row[-2] is not None)
            )
            if net > 0:
                order.append((net, row, counts))
        for net, row, counts in sorted(order, key=lambda a: (-a[0], a[1][0], a[1][1])):
            run, tok, pc, v, stamp, pid, other, ts = row
            if tok in events or occupied.intersection(ts):
                continue
            occupied.update(ts)
            events.add(tok)
            selected.append(
                {
                    "run": run,
                    "source": tok,
                    "op": pc,
                    "version": v,
                    "stamp": stamp,
                    "recipe": pid,
                    "other": other,
                    "other_stamp": stamps[other] if other else None,
                    "steps": ts,
                    "fresh_path_counts": counts,
                    "ranking_surplus": net,
                }
            )
        dump(store / (program["recipe"]["sha256"] + "-receipts.json"), selected)
    return maps, contract


def analyze(data, store, case):
    program = read(folder(data, case) / "program.json")
    tape = read(store / f"{case}-issued.json")
    q = {a["token"]: a for a in tape["requests"]}
    z = np.load(store / f"{case}-ledger.npz")
    other = np.load(store / f"{case}-single-ledger.npz")
    if not np.array_equal(z["meta"], other["meta"]) or not np.array_equal(
        z["verdict"][:, :-2], other["verdict"][:, :-2]
    ):
        raise ValueError("singleton proof population changed")
    meta = z["meta"]
    depth = z["depth"]
    costs = depth[:, :, 1].sum(1)
    oldcost = depth[:, :, 2].sum(1)
    order = np.argsort(-costs, kind="stable")
    top = order[: 1 + np.searchsorted(costs[order].cumsum(), costs.sum() * 0.95)]
    wanted = set(map(int, top))
    proofs = defaultdict(set)
    for t, i in z["winners"]:
        if i in wanted:
            proofs[int(i)].add(tuple(map(named, q[t]["parents"])))
    with gzip.open(store / f"{case}-single-duplicate-witnesses.jsonl.gz", "rt") as f:
        for line in f:
            eid, refs = json.loads(line)
            if eid in wanted:
                proofs[eid].add(tuple(map(tuple, refs)))
    exact = read(store / f"{case}-exact-audit.json")
    for i, why, owner, loss, refs in exact["witnesses"]:
        if why in ("match", "off_reference"):
            proofs[i].add(tuple(map(tuple, refs)))
    compiled, contract = compiled_outputs(case, data, store, program, q, tape)
    from txn_policy import request_frontier

    def computable_fields(r, j):
        states = ["unbound"] * len(contract["rules"][r]["inputs"])
        states[j] = "available"
        return sum(
            len(v)
            for v in request_frontier(contract["rules"][r], states, chains=True)["computations"].values()
        )

    computable_fields = lru_cache(None)(computable_fields)
    rollout = read(store / f"{case}-profile-0.json")
    open_receipts = {tuple(ref) for _, _, _, ports in rollout["published_recursive"] for ref in ports}
    joint = defaultdict(set)
    for structure in rollout["structures"]:
        for t in structure["tokens"]:
            joint[t].update(structure["tokens"])

    @lru_cache(None)
    def ancestors(t):
        direct = {named(p)[0] for p in q.get(t, {}).get("parents", ())}
        return direct.union(*(ancestors(v) for v in direct))

    rule_fd = lru_cache(None)(lambda r, j: dependencies(program["recipe"]["rules"][r], j))
    categories = Counter()
    weighted = Counter()
    native = Counter()
    cols = Counter()
    shared = defaultdict(set)
    stages = defaultdict(set)
    prune = z["prune"]
    evidence_examples = []
    for i in top:
        run, r, j, t, _, v = map(int, meta[i, :6])
        cost = int(costs[i])
        observed = proofs.get(i, ())
        if j >= 0 and computable_fields(r, j):
            native["actual_compiled_computation_request_available_events"] += 1
            native["actual_compiled_computation_request_available_cost"] += cost
        if not observed:
            fork = exact["runs"][str(run)]
            label = (
                "fork_failed"
                if "error" in fork
                else "exact_fork_emitted_no_rule_binding"
                if not fork["rules"].get(str(r), 0)
                else "unresolved_no_named_witness"
            )
            if prune[i] == 1:
                label = "valid_pruned_witness"
            categories[label] += 1
            weighted[label] += cost
            continue
        best = None
        for refs in observed:
            needs = set()
            labels = []
            for ref in refs:
                parent = ref[0]
                if parent == t:
                    label = "source_named_port"
                elif parent in ancestors(t):
                    label = "signed_ancestor"
                elif parent in joint.get(t, ()):
                    label = "same_ripsat_receipt"
                elif ref in compiled.get((t, None), ()):
                    label = "certified_compiled_receipt"
                else:
                    label = (
                        "other_open_ripsat_requires_address"
                        if ref in open_receipts
                        else "independent_in_tested_interfaces"
                    )
                    needs.add(ref)
                labels.append(label)
            if len(needs) > 1:
                for ext in sorted(needs):
                    rem = needs - compiled.get((t, ext), set())
                    if len(rem) < len(needs):
                        labels = [
                            "certified_compiled_receipt" if p in needs - rem else l
                            for l, p in zip(labels, refs)
                        ]
                        needs = rem
                        break
            candidate = (len(needs), tuple(sorted(needs)), tuple(labels), refs)
            if best is None or candidate < best:
                best = candidate
        n, needs, labels, refs = best
        unique, computed = rule_fd(r, j)
        for label in labels:
            cols[label] += 1
        label = "named_wiring" if not n else "one_external" if n == 1 else "multiple_external"
        if n == 1:
            key = (t, v, needs[0])
            shared[key].add((run, r, int(i)))
            stages[key].add(run)
        categories[label] += 1
        weighted[label] += cost
        if computed:
            native["event_cost_with_scalar_fd"] += cost
        if not n and unique:
            native["one_witness_fixes_signature_cost_ceiling"] += cost
        if not n:
            native["one_witness_does_not_certify_all_residual_scores"] += cost - int(oldcost[i])
        evidence_examples.append([int(i), int(n), bool(unique), cost, int(oldcost[i]), list(labels)])
    for k, events in shared.items():
        cost = sum(int(costs[i]) for _, _, i in events)
        if len({r for _, r, _ in events}) > 1:
            native["potential_shared_binding_event_cost"] += cost
        if len(stages[k]) > 1:
            native["potential_cross_run_event_cost"] += cost
    dump(
        store / f"{case}-dependencies.json",
        {
            "high95_events": len(top),
            "high95_cost": int(costs[top].sum()),
            "certified_old_cost": int(oldcost[top].sum()),
            "events": categories,
            "cost": weighted,
            "parent_roles": cols,
            "conditional_ceilings": native,
            "examined_witnesses": sum(map(len, proofs.values())),
            "examples": evidence_examples,
        },
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("data", type=Path)
    p.add_argument("store", type=Path)
    p.add_argument("cases", nargs="+")
    a = p.parse_args()
    for case in a.cases:
        analyze(a.data, a.store, case)
