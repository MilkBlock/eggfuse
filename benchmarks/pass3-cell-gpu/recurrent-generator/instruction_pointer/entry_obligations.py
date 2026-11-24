"""Find the first unmet obligation per observed instance of a frozen specialization."""

import argparse
import csv
from collections import Counter
from pathlib import Path

from receipt_bake import Snapshot, address, read, save
from ripsat_layout import capture
from ripsat_replay import unpack


def diagnose(unit, tokens, requests, snapshot, schedules):
    first = requests[tokens[0]]["run"]
    previous = first
    external = {}
    # All boundary references, even ones first consumed later, must exist at entry.
    for step, (rid, group, wires) in enumerate(unit):
        q = requests[tokens[step]]
        for role, ((owner, pc), arg) in enumerate(
            zip(wires, q["parents"], strict=True)
        ):
            t, op = address(arg)
            v = arg["version"]
            if owner >= 0:
                continue
            if pc in external and external[pc] != (t, op, v):
                return "entry_alias_conflict"
            external[pc] = (t, op, v)
    for t, op, v in external.values():
        actual = snapshot.version(t, op, first)
        if actual != v:
            if actual is not None:
                return "entry_version_differs"
            if any(r <= first for r, _ in snapshot.timeline[t, op]):
                return "entry_retired"
            return "external_receipt_not_yet_visible"
    for i, (_, g, wires) in enumerate(unit):
        q = requests[tokens[i]]
        if i and g != unit[i - 1][1]:
            group = {
                requests[tokens[j]]["rule"] for j, s in enumerate(unit) if s[1] == g
            }
            if (
                next(
                    (
                        r
                        for r in range(previous + 1, q["run"] + 1)
                        if group <= schedules[r]
                    ),
                    None,
                )
                != q["run"]
            ):
                return "earlier_eligible_schedule"
            previous = q["run"]
        for (owner, pc), arg in zip(wires, q["parents"], strict=True):
            if owner < 0:
                continue
            t = tokens[owner]
            if (t, pc) != address(arg):
                return "different_internal_witness"
            ver = snapshot.version(t, pc, requests[t]["run"] + 1)
            if ver is None:
                return "internal_receipt_unavailable_at_publication"
            if ver != arg["version"]:
                return "internal_version_changed"
    return "ready"


def audit(root, original, frozen, slots, out):
    import json

    old = unpack(read(original)["layouts"])
    new = unpack(read(frozen)["layouts"])
    with slots.open() as stream:
        cohort = [
            int(a["uid"])
            for a in csv.DictReader(stream)
            if int(a["before"]) > int(a["after"])
            and not int(a["train_ready_before"])
            and not int(a["frozen_train_occurrences"])
        ]
    ids = {old[i]: i for i in cohort}
    counts = {i: Counter() for i in ids.values()}
    witnesses = {}
    donor = read(root / "sum/program.json")
    for name in ("sum", "dot"):
        folder = root / name
        refs, _, roots, _ = capture(folder, donor, 10, grow_consumers=True)
        req = {q["token"]: q for q in refs}
        snap = Snapshot(folder)
        schedules = {
            f["run"]: {r for r, _ in f["rules"]}
            for f in map(json.loads, (folder / "memory.jsonl").open())
        }
        for variants in roots.values():
            for u in ids.keys() & variants.keys():
                i = ids[u]
                for _, _, _, ts in variants[u]:
                    why = diagnose(new[i], ts, req, snap, schedules)
                    counts[i][why] += 1
                    witnesses.setdefault((i, why), (name, ts[0], req[ts[0]]["run"]))
    if any(not c or c["ready"] for c in counts.values()):
        raise ValueError("unexplained or ready template")
    save(
        out,
        dict(
            templates=len(ids),
            occurrences=sum(counts.values(), Counter()),
            dominant=Counter(min(c, key=lambda k: (-c[k], k)) for c in counts.values()),
            rows={
                i: dict(counts=c, examples={k: witnesses[i, k] for k in c})
                for i, c in counts.items()
            },
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for k in ("root", "original", "frozen", "slots", "output"):
        p.add_argument(k, type=Path)
    a = p.parse_args()
    audit(a.root, a.original, a.frozen, a.slots, a.output)
