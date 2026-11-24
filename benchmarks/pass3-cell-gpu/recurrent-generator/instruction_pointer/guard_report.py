"""Summarize independent rollouts and replay sealed Runs for semantic coverage curves."""

import argparse
import csv
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

from recursive_coverage import Target, snapshot
from recursive_train import binary, folder, read

CASES = (
    "cyk801",
    "grammar-4691132",
    "grammar-72102993",
    "grammar-layout-832749",
    "fact",
    "loopfact",
    "sum-divisors",
    "jacobi",
)
ARMS = (
    "control",
    "joint-recall",
    "joint-balanced",
    "s8",
    "s4",
    "s4-recall",
    "p8",
    "p8-delta",
)
EXTRA_WORK = ("index_items", "bucket_items", "bucket_probes")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def native_history(root, d, mode, tape, dest, limit=None, detail="time"):
    cmd = [binary(root), mode, d / "program.json", tape, detail]
    if limit is not None:
        cmd.append(str(limit))
    return json.loads(subprocess.check_output(cmd + ["--row-history", dest]))


def attribute(root, dest, tmp):
    d = folder(root, "cyk801")
    w = root / "guard-control/cyk801-stream-multi"
    m = read(w / "metrics.json")
    teacher = native_history(
        root, d, "reference", "-", tmp / "teacher.jsonl", detail="audit"
    )
    actual = native_history(
        root, d, "replay", w / "issued.json", tmp / "audit.jsonl", detail="audit"
    )
    rows_equal = digest(tmp / "teacher.jsonl") == digest(tmp / "audit.jsonl")
    fields = {
        k: teacher[k] == actual[k] for k in ("state_sha", "rhs", "schedule", "writes")
    }
    counts = Counter()
    for _, rule, atom, reason, n in m["guard_failures"]:
        counts[rule, atom, reason] += n
    assert sum(counts.values()) == m["verdicts"]["guard"]
    accepts = Counter(
        (r["run"], r["rule"]) for r in read(w / "issued.json")["requests"]
    )
    (dest / "guard-attribution.json").write_text(
        json.dumps(
            dict(
                run_rule_atom_reason_counts=m["guard_failures"],
                run_rule_accepted=[[*k, n] for k, n in sorted(accepts.items())],
                totals=[[*k, n] for k, n in sorted(counts.items())],
                replay_equal=fields,
                identical_row_history=rows_equal,
                teacher_rows_sha=digest(tmp / "teacher.jsonl"),
                actual_rows_sha=digest(tmp / "audit.jsonl"),
            ),
            indent=2,
        )
        + "\n"
    )


def summarize_operating_points(root, dest, rows):
    # Compare only completed executions of a given program. EPS on a divergent
    # graph can include work that covers none of the reference facts.
    frontier = {}
    for case in CASES:
        complete = [
            r for r in rows if r["case"] == case and r["termination"] == "schedule_end"
        ]

        def dominates(a, b):
            dims = ("derived", "eps", "ept")
            return all(a[k] >= b[k] for k in dims) and any(a[k] > b[k] for k in dims)

        frontier[case] = [
            r["policy"] for r in complete if not any(dominates(a, r) for a in complete)
        ]
    (dest / "frontier.json").write_text(json.dumps(frontier, indent=2) + "\n")
    access = {}
    for policy in ("control", "p8", "p8-delta"):
        path = root / ("guard-" + policy) / "cyk801-stream-multi/metrics.json"
        m = read(path)
        if "traversed_positions" not in m["work"]:
            m = read(
                root / ("guard-touch-" + policy) / "cyk801-stream-multi/metrics.json"
            )
        access[policy] = {
            k: m[k]
            for k in (
                "work",
                "paid",
                "state_sha",
                "signed_ops",
                "ept",
                "eps",
                "exact_endpoint",
                "wall",
                "verdicts",
            )
        }
    (dest / "access.json").write_text(json.dumps(access, indent=2) + "\n")


def summarize(root, dest):
    dest.mkdir(parents=True, exist_ok=True)
    all_rows = []
    curves = []
    with TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        attribute(root, dest, tmp)
        for case in CASES:
            d = folder(root, case)
            target, ref = snapshot(root, d, "reference", "-", None, tmp / "ref.json")
            goal = Target(read(d / "program.json"), target)
            initial, _ = snapshot(root, d, "reference", "-", 0, tmp / "init.json")
            seed = goal.match(initial)
            denominator = len(goal.gold) - len(seed)
            assert len(goal.match(target)) == len(goal.gold)
            for arm in (*ARMS, *(("p4",) if case == "grammar-4691132" else ())):
                w = root / ("guard-" + arm) / (case + "-stream-multi")
                m = read(w / "metrics.json")
                state = read(w / "state.json")
                cover = len(goal.match(state) - seed)
                work = m["work"]
                assert sum(m["verdicts"].values()) == m["paid"] and denominator > 0
                row = dict(
                    case=case,
                    policy=arm,
                    derived=cover,
                    reference=denominator,
                    reference_commits=ref["matches"],
                    reference_runs=ref["runs"],
                    **{
                        k: v
                        for k, v in m.items()
                        if k not in ("case", "arm", "phase", "trace", "guard_failures")
                    },
                )
                row["scored_and_interfaces"] = work["visits"] + work["interface_reads"]
                row["including_index_touches"] = row["scored_and_interfaces"] + sum(
                    work.get(k, 0) for k in EXTRA_WORK
                )
                all_rows.append(row)
                # Curves use the same frozen gold labels at every completed native boundary.
                log = tmp / "arm.jsonl"
                replay = native_history(
                    root, d, "replay", w / "issued.json", log, m["runs"]
                )
                assert replay["state_sha"] == m["state_sha"]
                alive = {}
                count = 0
                with log.open() as f:
                    for line in f:
                        frame = json.loads(line)
                        for key in frame["removed"]:
                            del alive[key]
                        for key in frame["added"]:
                            alive[key] = json.loads(key)
                        if frame["removed"] or frame["added"] or frame["run"] == 0:
                            count = len(goal.match({"rows": alive.values()}) - seed)
                        t = m["trace"][frame["run"] - 1] if frame["run"] else {}
                        curves.append(
                            (
                                case,
                                arm,
                                frame["run"],
                                t.get("elapsed", 0),
                                t.get("paid", 0),
                                t.get("visits", 0) + t.get("interface_reads", 0),
                                count,
                                denominator,
                            )
                        )
                assert count == cover
                curves.append(
                    (
                        case,
                        arm,
                        m["runs"],
                        m["wall"],
                        m["paid"],
                        row["scored_and_interfaces"],
                        cover,
                        denominator,
                    )
                )
            print(case, flush=True)
    with (dest / "runs.csv").open("w") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(
            [
                "case",
                "policy",
                "sealed_runs",
                "seconds",
                "paid",
                "scored_and_interfaces",
                "derived",
                "reference",
            ]
        )
        writer.writerows(curves)
    (dest / "results.json").write_text(json.dumps(all_rows, indent=2) + "\n")
    summarize_operating_points(root, dest, all_rows)
    files = {
        "binary": binary(root),
        "compose": root / "recursive-agent/multi.pt",
        "field": root / "structured-retrieval/field.pt",
        "joint": root / "guard-study/joint.pt",
    }
    files.update({case: folder(root, case) / "program.json" for case in CASES})
    (dest / "provenance.json").write_text(
        json.dumps({k: digest(p) for k, p in files.items()}, indent=2) + "\n"
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("dest", type=Path)
    a = p.parse_args()
    summarize(a.root.resolve(), a.dest)
