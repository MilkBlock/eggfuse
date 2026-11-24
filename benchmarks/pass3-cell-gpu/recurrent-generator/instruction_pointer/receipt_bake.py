"""Specialize a frozen layout using typed native return sites. Training tapes propose
links. A specialization is a separate proof shape; ordinary source bindings remain legal.
"""

import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import subprocess

from anchor_set_audit import check
from int_parameters import StructuralBake, link_layouts
from ripsat_layout import capture
from ripsat_replay import unpack
from side_boundary import address


def read(p):
    return json.loads(p.read_bytes())


def save(p, obj):
    p.write_text(json.dumps(obj, separators=(",", ":")) + "\n")


def external(unit):
    return {s for _, _, w in unit for owner, s in w if owner < 0}


def specialize(unit, boundary, tokens, contract):
    locations = {token: i for i, token in enumerate(tokens)}
    refs = {}
    for j, (rid, group, wires) in enumerate(unit):
        for role, (owner, slot) in enumerate(wires):
            if owner >= 0:
                continue
            token, pc, _ = boundary[slot]
            source = locations.get(token)
            if source is None or unit[source][1] >= group:
                refs[slot] = None
                continue
            ret = contract[unit[source][0]]["outputs"].get(str(pc))
            required = contract[rid]["inputs"][role]["table"]
            if ret and ret.get("merge_op") is not None and ret["table"] == required:
                refs.setdefault(slot, (source, pc))
            else:
                refs[slot] = None
    new_slots = {}
    steps = []
    for rid, group, wires in unit:
        updated = []
        for owner, slot in wires:
            if owner >= 0:
                updated.append((owner, slot))
            elif refs.get(slot) is not None:
                updated.append(refs[slot])
            else:
                updated.append((-1, new_slots.setdefault(slot, len(new_slots))))
        steps.append((rid, group, tuple(updated)))
    return tuple(steps), tuple(boundary[k] for k in new_slots)


class Snapshot:
    def __init__(self, folder):
        self.timeline = defaultdict(list)
        for line in (folder / "memory.jsonl").read_bytes().splitlines():
            frame = json.loads(line)
            for a in frame["retired"]:
                self.timeline[a["token"], a["op"]].append((frame["run"], None))
            for a, r in frame["updates"]:
                self.timeline[a["token"], a["op"]].append((frame["run"], r["version"]))

    def version(self, token, pc, run):
        rows = self.timeline[token, pc]
        i = bisect_right(rows, run, key=lambda r: r[0]) - 1
        return rows[i][1] if i >= 0 else None


def prove(unit, boundary, tokens, requests, snapshot):
    root_run = requests[tokens[0]]["run"]
    for t, pc, v in boundary:
        if snapshot.version(t, pc, root_run) != v:
            return None
    steps = []
    for tok, (_, _, wires) in zip(tokens, unit, strict=True):
        q = requests[tok]
        parents = []
        for (owner, pc), original in zip(wires, q["parents"], strict=True):
            if owner < 0:
                t, op, v = boundary[pc]
            else:
                t, op = tokens[owner], pc
                v = snapshot.version(t, op, requests[t]["run"] + 1)
            if v is None or (*address(original), original["version"]) != (t, op, v):
                return None
            parents.append(dict(address=dict(token=t, op=op), version=v))
        steps.append(dict(rule=q["rule"], run=q["run"], parents=parents))
    return steps


def audit(root, catalog_path, binary, out):
    out.mkdir(exist_ok=True, parents=True)
    catalog = read(catalog_path)
    donor = read(root / "sum/program.json")
    originals = unpack(catalog["layouts"])
    learned = defaultdict(Counter)
    train_ready = set()
    result = {}
    details = [Counter() for _ in originals]
    frozen = {}
    feasible_training = defaultdict(Counter)
    for name in ("sum", "dot", "fact", "loopfact", "sum-divisors"):
        training = name in ("sum", "dot")
        program_path = root / name / "program.json"
        target = read(program_path)
        native = json.loads(
            subprocess.check_output([binary, "receipt-contract", program_path])
        )
        if native["recipe_sha256"] != target["recipe"]["sha256"]:
            raise ValueError("stale native contract")
        if training:
            refs, mapped, roots, _ = capture(
                root / name, donor, 10, grow_consumers=True
            )
            lookup = {u: [i] for i, u in enumerate(originals)}
        else:
            refs, mapped, roots, _ = capture(
                root / name, target, 10, grow_consumers=True
            )
            lookup = defaultdict(list)
            for i, u in link_layouts(target, catalog):
                lookup[tuple(u)].append(i)
        snapshot = Snapshot(root / name)
        requests = {q["token"]: q for q in refs}
        before, after, new_only, actual = set(), set(), set(), set()
        root_before, root_after = set(), set()
        probes, expected = [], []
        sampled = set()
        counts = Counter()
        for j, choices in roots.items():
            for key, occ in choices.items():
                for uid in lookup.get(key, ()):
                    for b, ready, scheduled, tokens in occ:
                        u = tuple(
                            (requests[t]["rule"], g, w)
                            for t, (_, g, w) in zip(tokens, key, strict=True)
                        )
                        new, bb = specialize(u, b, tokens, native["rules"])
                        donor_new = tuple(
                            (r, g, w)
                            for (r, _, _), (_, g, w) in zip(
                                originals[uid], new, strict=True
                            )
                        )
                        if training and donor_new != originals[uid]:
                            learned[uid][donor_new] += 1
                        selected = training or frozen.get(uid) == donor_new
                        if ready and scheduled:
                            before.add(uid)
                            root_before.add((uid, j))
                            if training:
                                train_ready.add(uid)
                        if not scheduled:
                            continue
                        if not ready and not (new != u and selected):
                            continue
                        steps = (
                            prove(new, bb, tokens, requests, snapshot)
                            if selected
                            else None
                        )
                        if ready or steps:
                            after.add(uid)
                            root_after.add((uid, j))
                        if steps and new != u and selected:
                            if training:
                                feasible_training[uid, donor_new][name] += 1
                            actual.add(uid)
                            details[uid][name + "_ready_specialization"] += 1
                            if not ready:
                                new_only.add(uid)
                            # Native teacher-shadow probes, including every sampled
                            # context of regression 4790 and one per other layout.
                            if training or (uid in sampled and uid != 4790):
                                continue
                            sampled.add(uid)
                            for step, t in zip(steps, tokens, strict=True):
                                probes.append(dict(step, token=len(probes) + 1))
                                expected.append(t)
                            if uid == 4790:
                                counts["4790_verified_instances"] += 1
        if probes:
            raw = check(root / name, binary, read(root / name / "tape.json"), probes)
            verdict = {i: t for _, i, t, _ in raw["recall_verdicts"]}
            if any(verdict[i] != t for i, t in enumerate(expected, 1)):
                raise ValueError("native verifier did not return the intended binding")
        if name == "dot":
            frozen = {
                i: min(opts, key=lambda u: (-opts[u], u)) for i, opts in learned.items()
            }
            variants = [frozen.get(i, u) for i, u in enumerate(originals)]
            manifest = dict(catalog, layouts=variants)
            manifest.update(StructuralBake(donor).manifest(variants))
            save(out / "catalog.json", manifest)
        counts.update(
            original_ready=len(before),
            either_ready=len(after),
            ready_added=len(after - before),
            ready_specializations=len(actual),
            freshly_ready_occurrence_templates=len(new_only),
            original_template_root_pairs=len(root_before),
            either_template_root_pairs=len(root_after),
            native_named_step_probes=len(probes),
            native_distinct_templates=len(sampled),
        )
        result[name] = counts
        print(name, dict(counts), flush=True)
    rows = []
    for i, u in enumerate(originals):
        v = frozen.get(i, u)
        rows.append(
            dict(
                uid=i,
                before=len(external(u)),
                after=len(external(v)),
                variants=len(learned.get(i, ())),
                train_ready_before=int(i in train_ready),
                frozen_train_occurrences=sum(
                    feasible_training.get((i, v), {}).values()
                ),
                **{n: details[i][n + "_ready_specialization"] for n in result},
            )
        )
    with (out / "slots.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    save(
        out / "audit.json",
        dict(
            programs=result,
            templates=len(rows),
            specialized=len(frozen),
            static_before=sum(r["before"] for r in rows),
            static_after=sum(r["after"] for r in rows),
            previously_never_ready=len(rows) - len(train_ready),
            never_ready_with_producer=sum(i not in train_ready for i in frozen),
            never_ready_with_ready_instance=sum(
                i not in train_ready and bool(feasible_training.get((i, v)))
                for i, v in frozen.items()
            ),
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for key in ("root", "catalog", "binary", "out"):
        p.add_argument(key, type=Path)
    a = p.parse_args()
    audit(a.root, a.catalog, a.binary, a.out)
