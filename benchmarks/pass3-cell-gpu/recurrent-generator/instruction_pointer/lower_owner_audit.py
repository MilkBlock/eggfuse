"""Native low-owner counterproofs and static point closure on recorded high-owner commits."""

import argparse
from collections import Counter, defaultdict
from itertools import product, islice
import json
from pathlib import Path

from alternate_proofs import addr
from anchor_set_audit import check
from higher_cell import read


def low_proofs(domains):
    if any(not d for d in domains):
        return
    by_owner = []
    for domain in domains:
        grouped = defaultdict(list)
        for key in domain:
            grouped[key[0]].append(key)
        by_owner.append(grouped)
    for first in by_owner[0]:
        missing = [d for d in by_owner if first not in d]
        seconds = (
            set.intersection(*(set(d) for d in missing))
            if missing
            else set.union(*(set(d) for d in by_owner))
        )
        for other in sorted(seconds | ({first} if not missing else set())):
            pools = [
                d.get(first, []) + (d.get(other, []) if other != first else [])
                for d in by_owner
            ]
            pools[0] = by_owner[0][first]
            for row in product(*pools):
                if other == first or any(t == other for t, _ in row):
                    yield row


def closure(query, parents, seed):
    bound = set()
    remaining = []
    it = iter(parents)
    for a in query:
        owner = next(it) if "table" in a["call"] else None
        slots = [v.get("slot") for v in a["args"]]
        if owner in seed:
            bound.update(slots)
        else:
            remaining.append((owner, slots))
    bound.add(None)
    while True:
        pending = [
            (t, cols) for t, cols in remaining if not all(c in bound for c in cols[:-1])
        ]
        if len(pending) == len(remaining):
            break
        for _, cols in remaining:
            if all(c in bound for c in cols[:-1]):
                bound.update(cols)
        remaining = pending
    return len(set(parents) - set(seed) - {t for t, _ in remaining})


def measure(folder, binary, budget):
    tape = read(folder / "tape.json")
    program = read(folder / "program.json")
    tables = {t["name"]: i for i, t in enumerate(program["recipe"]["tables"])}
    high = defaultdict(list)
    for q in tape["requests"]:
        if len({addr(p["address"])[0] for p in q["parents"]}) > 2:
            high[q["run"]].append(q)
    probes = []
    complete = set()
    targets = set()
    point = Counter()
    by_arity = Counter()
    visible = {}
    with (folder / "memory.jsonl").open() as f:
        for frame in map(json.loads, f):
            for a in frame["retired"]:
                del visible[addr(a)]
            for a, row in frame["updates"]:
                visible[addr(a)] = row
            run = frame["run"]
            wm = dict(frame["rules"])
            if run not in high:
                continue
            exact = defaultdict(list)
            typed = defaultdict(list)
            for key, row in visible.items():
                exact[row["table"], tuple(row["hashes"])].append(key)
                typed[row["table"]].append(key)
            seen = set()

            def emit(rid, keys):
                if (rid, keys) in seen:
                    return
                seen.add((rid, keys))
                probes.append(
                    dict(
                        rule=rid,
                        run=run,
                        token=len(probes) + 1,
                        parents=[
                            dict(
                                address=dict(token=t, op=k),
                                version=visible[t, k]["version"],
                            )
                            for t, k in keys
                        ],
                    )
                )

            group = defaultdict(list)
            for q in high[run]:
                rid = q["rule"]
                group[rid].append(q["token"])
                targets.add(q["token"])
                keys = [addr(p["address"]) for p in q["parents"]]
                owners = [t for t, k in keys]
                primary = next(
                    (t for t, k in keys if visible[t, k]["version"] >= wm[rid]),
                    owners[0],
                )
                seeds = [primary, next(t for t in owners if t != primary)]
                n = len(set(owners))
                by_arity[n] += 1
                determined = closure(
                    program["recipe"]["rules"][rid]["query"], owners, seeds
                )
                point["remaining"] += n - 2
                point["determined"] += determined
                point["all"] += determined == n - 2
                dom = [
                    exact[visible[k]["table"], tuple(visible[k]["hashes"])]
                    for k in keys
                ]
                for row in islice(low_proofs(dom), budget):
                    emit(rid, row)
            for rid, ts in group.items():
                dom = [
                    typed[tables[a["call"]["table"]]]
                    for a in program["recipe"]["rules"][rid]["query"]
                    if "table" in a["call"]
                ]
                proofs = list(islice(low_proofs(dom), budget + 1))
                if len(proofs) <= budget:
                    complete.update(ts)
                for row in proofs[:budget]:
                    emit(rid, row)
    result = check(folder, binary, tape, probes)
    found = {w for _, _, w, _ in result["recall_verdicts"] if w in targets}
    return dict(
        high=len(targets),
        by_arity=by_arity,
        found=len(found),
        exhausted_negative=len(complete - found),
        unknown=len(targets - found - complete),
        budget=budget,
        probes=len(probes),
        point=point,
        found_ids=sorted(found),
        negative_ids=sorted(complete - found),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for k in ("folder", "binary", "output"):
        p.add_argument(k, type=Path)
    p.add_argument("--budget", type=int, default=128)
    a = p.parse_args()
    a.output.write_text(
        json.dumps(measure(a.folder, a.binary, a.budget), indent=2) + "\n"
    )
