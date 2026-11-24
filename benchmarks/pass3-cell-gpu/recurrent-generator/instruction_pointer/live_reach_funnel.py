"""Offline next-Run forks on an unchanged independent A tape; shadow counters cannot issue."""

import argparse, hashlib, json, subprocess
from collections import Counter, defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory
import numpy as np
import torch
from generation_frontier import Generator
from txn_policy import ResponseStream
from protocol_experiment import dump
from recursive_train import binary, folder, read
from transaction_native import execute


def ref(a):
    return a["address"]["token"], a["address"]["op"], a["version"]


def key(q):
    return q["run"], q["rule"], tuple(map(ref, q["parents"]))


class Watch(ResponseStream):
    def path_batches(self, *args, **kwargs):
        self.watch = []
        selected = self.study.targets.get((self.transaction.run, self.rule), [])
        if selected:
            lookup = [{a: i for i, a in enumerate(ports)} for ports in self.roles]
            for req in selected:
                addr = tuple(map(ref, req["parents"]))
                k = key(req)
                if len(addr) != len(self.order):
                    self.study.outcome[k] = "unexpressible"
                    continue
                path = []
                versions = []
                for j, role in enumerate(self.order):
                    t, op, v = addr[role]
                    if (t, op) not in lookup[j] or self.rd.store.visible[t, op][
                        "version"
                    ] != v:
                        break
                    path.append(lookup[j][t, op])
                    versions.append(v)
                else:
                    if self.semi and versions and max(versions) < self.wm:
                        self.study.outcome[k] = "watermark"
                        continue
                    self.watch.append((k, tuple(path)))
                    self.study.outcome[k] = "retrieval"
                    continue
                self.study.outcome[k] = "parents_not_visible"
        for paths in super().path_batches(*args, **kwargs):
            if self.watch:
                present = set(map(tuple, paths.tolist()))
                for k, p in self.watch:
                    if p in present:
                        self.study.outcome[k] = "issued"
            yield paths

    def score_children(self, h, depth, paths, parents):
        score, z = super().score_children(h, depth, paths, parents)
        if self.watch:
            wanted = {p[: depth + 1] for _, p in self.watch}
            scored = {
                p: s
                for p, s in zip(map(tuple, paths.tolist()), score.tolist())
                if p in wanted
            }
            for k, p in self.watch:
                value = scored.get(p[: depth + 1])
                if value is not None:
                    self.study.outcome[k] = (
                        ("final_gate" if depth + 1 == len(p) else "prefix_gate")
                        if value < 0
                        else "retrieval"
                    )
        return score, z


def signatures(tape):
    names = {}

    def parent(t):
        if t in names:
            return names[t]
        return f"seed:{t}" if t < 0 and t % 2 else None

    events = sorted(
        [(q["run"], 1, q) for q in tape["requests"]]
        + [(q["visible_from_run"], 0, q) for q in tape.get("repair_events", [])],
        key=lambda x: x[:2],
    )
    for _, normal, q in events:
        roles = [
            (parent(p["address"]["token"]), p["address"]["op"]) for p in q["parents"]
        ]
        if all(a is not None for a, b in roles):
            names[q["token"]] = hashlib.sha256(
                repr(
                    (normal, q["rule"] if normal else q["merge_table"], roles)
                ).encode()
            ).hexdigest()
    return parent


def reference_visibility(teacher, own, frames, selected):
    tn, on = map(signatures, (teacher, own))
    by = defaultdict(list)
    for q in teacher["requests"]:
        if q["run"] in selected:
            by[q["run"]].append(q)
    rows = {}
    cnt = Counter()
    for frame in frames:
        for a in frame["retired"]:
            rows.pop((a["token"], a["op"]), None)
        for a, r in frame["updates"]:
            rows[a["token"], a["op"]] = r["version"]
        if frame["run"] not in by:
            continue
        lookup = {(on(t), op) for t, op in rows if on(t) is not None}
        aged = {(on(t), op, v) for (t, op), v in rows.items() if on(t) is not None}
        scheduled = dict(frame["rules"])
        for q in by[frame["run"]]:
            refs = [(tn(t), op, v) for t, op, v in map(ref, q["parents"])]
            why = "same_provenance_and_version"
            if q["rule"] not in scheduled:
                why = "different_schedule"
            elif any(t is None for t, _, _ in refs):
                why = "unknown_parent"
            elif not all((t, op) in lookup for t, op, v in refs):
                why = "recorded_parent_lineage_absent"
            elif not all(r in aged for r in refs):
                why = "version_differs"
            cnt[why] += 1
    return dict(cnt)


def audit(root, out, case, exe, all_runs=False):
    d = folder(root, case)
    work = root / "generation-frontier/A-0" / (case + "-stream-multi")
    gold = read(work / "issued.json")
    baseline = read(work / "metrics.json")
    by = sorted({q["run"] for q in gold["requests"]})
    runs = sorted(
        set(range(1, min(17, baseline["runs"] + 1)))
        | {by[i] for i in np.linspace(0, len(by) - 1, min(35, len(by)), dtype=int)}
        | set(np.linspace(1, baseline["runs"], 24, dtype=int).tolist())
    )
    if all_runs:
        runs = range(1, baseline["runs"] + 1)
    targets = defaultdict(list)
    probes = []
    errors = {}
    for r in runs:
        proc = subprocess.run(
            [
                exe,
                "replay",
                d / "program.json",
                work / "issued.json",
                "time",
                str(r - 1),
                "--audit-next-proofs",
            ],
            capture_output=True,
        )
        if proc.returncode:
            errors[int(r)] = proc.stderr.decode()[-200:]
            continue
        for q in json.loads(proc.stdout):
            q["token"] = len(probes) + 1
            probes.append(q)
            targets[r, q["rule"]].append(q)
    g = Generator(root, "A", 0, case)
    g.targets = targets
    g.outcome = {}
    g.stream_type = Watch
    m = execute(root, case, study=g, series="structural-funnel", seconds=240)
    assert m["state_sha"] == baseline["state_sha"] and m["paid"] == baseline["paid"]
    fresh = root / "structural-funnel" / (case + "-stream-multi") / "issued.json"
    assert read(fresh) == gold
    with TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        probe = tmp / "audit.json"
        memory = tmp / "frames.jsonl"
        dump(probe, {**gold, "requests": probes})
        report = json.loads(
            subprocess.check_output(
                [
                    exe,
                    "replay",
                    d / "program.json",
                    fresh,
                    "time",
                    "--memory",
                    memory,
                    "--recall",
                    probe,
                ]
            )
        )
        with memory.open() as lines:
            visibility = reference_visibility(
                read(d / "tape.json"), gold, map(json.loads, lines), set(runs)
            )
    winners = Counter()
    groups = Counter()
    byrun = defaultdict(Counter)
    reasons = Counter()
    for r, i, owner, why in report["recall_verdicts"]:
        q = probes[i - 1]
        k = key(q)
        stage = g.outcome.get(k, "unscheduled")
        winners[stage] += int(owner is not None)
        reasons[why] += 1
        if stage == "issued":
            stage = "accepted_binding" if owner is not None else "native_" + why
        groups[stage] += 1
        byrun[r][stage] += 1
    assert sum(groups.values()) == len(probes)
    dump(
        out / f"funnel-{case}{'-all' if all_runs else ''}.json",
        dict(
            runs=list(map(int, runs)),
            fork_errors=errors,
            targets=len(probes),
            first_loss=groups,
            by_run=byrun,
            won_by_any_proof=winners,
            native_reference_checks=reasons,
            teacher_parent_visibility=visibility,
            sha=m["state_sha"],
        ),
    )
    print(case, groups, errors, flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("exe", type=Path)
    p.add_argument("cases", nargs="+")
    p.add_argument("--all-runs", action="store_true")
    a = p.parse_args()
    torch.set_num_threads(1)
    for c in a.cases:
        audit(a.root, a.out, c, a.exe, a.all_runs)
