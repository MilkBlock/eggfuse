"""Verify joins and publish aggregate counts, evidence examples and measured independent runs."""

import argparse
import csv
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

from control_credit_experience import load, records
from dual_credit_pages import records as page_records


def read(path):
    if path.suffix == ".gz":
        with gzip.open(path) as f:
            return json.load(f)
    return json.loads(path.read_bytes())


def write(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")


def table(path, rows):
    with path.open("w") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def count_evidence(rows):
    n = Counter()
    for teacher, policy in rows:
        n["observations"] += 1
        if teacher is None or policy is None:
            n["unknown"] += 1
            continue
        n["positive_witness"] += teacher > 0
        n["positive_witness_zero_realized"] += teacher > 0 and policy == 0
        n["no_positive_witness"] += not teacher
        n["positive_policy"] += policy > 0
        n["witnessed_ops"] += teacher
        n["realized_ops"] += policy
    return dict(n)


def twins(root):
    return [row for f in sorted((root / "dual").glob("*.gz")) for row in read(f)]


def report(a):
    dest = a.dest
    dest.mkdir(parents=True, exist_ok=True)
    pairs = twins(a.out)
    by_state = {v["state"]: v for v in pairs}
    refreshed = twins(a.out / "refreshed")
    count = Counter()
    joined = set()
    for side in sorted((a.paired / "ledger").glob("*.gz")):
        sh = read(side)
        batch = [
            v
            for v in pairs
            if (v["program"], v["cohort"]) == (sh["program"], sh["cohort"])
        ]
        for r in records(sh, load(a.paired, "allocation", side.name), dual=batch):
            count["historical_" + r["kind"]] += 1
            if r.get("control_effect") is not None:
                joined.add(r["state"])
                count["signed_policy_preferences"] += r["masks"]["realized_allocation"]
    if joined != set(by_state) or len(joined) != len(pairs):
        raise ValueError("missing or duplicated exact-state joins")
    if {p.name for p in (a.out / "buffer").glob("*.gz")} != {
        p.name for p in (a.out / "page-dual").glob("*.gz")
    }:
        raise ValueError("incomplete same-window audit coverage")
    if not refreshed:
        raise ValueError("missing held-state updated-policy twins")
    page_measure = []
    for f in sorted((a.out / "page-dual").glob("*.gz")):
        for r in page_records(a.out / "buffer" / f.name, a.out / "credit" / f.name, f):
            count["new_" + r["kind"]] += 1
            if r["kind"] == "control":
                count["fixed_action_" + str(r["action"])] += 1
            if "teacher_witnesses" in r:
                w = r["teacher_witnesses"]
                page_measure.append(
                    (sum(n for _, n in w) if w is not None else None, r["realized_ops"])
                )

    def measured(rows):
        return count_evidence(
            [
                (
                    v["teacher_potential"]["witnessed_ops"],
                    v["policy_realization"]["continue"]["first_page_ops"],
                )
                for v in rows
            ]
        )

    flips = Counter()
    for v in refreshed:
        orig = by_state[v["state"]]
        if (
            orig["prefix"] != v["prefix"]
            or orig["teacher_potential"] != v["teacher_potential"]
            or orig["checkpoint"] == v["checkpoint"]
        ):
            raise ValueError("policy comparison not aligned")
        l, r = (
            t["policy_realization"]["continue"]["first_page_ops"] for t in (orig, v)
        )
        if l is None or r is None:
            flips["unknown"] += 1
        else:
            flips["better" if r > l else "worse" if r < l else "equal"] += 1
    summary = dict(
        fixed=count_evidence(page_measure),
        frozen_paired=measured(pairs),
        refreshed_paired=measured(refreshed),
        matched_initial=measured([by_state[v["state"]] for v in refreshed]),
        first_page_change=flips,
        record_counts=count,
    )
    allocations = []
    for version, observations in (("initial", pairs), ("refreshed", refreshed)):
        for row in observations:
            difference = row["control_effect"]
            left = row["policy_realization"]["continue"]
            right = row["policy_realization"]["seal"]
            allocations.append(
                dict(
                    policy=version,
                    state=row["state"],
                    signature=row["signature"],
                    run=row["run"],
                    teacher_ops=row["teacher_potential"]["witnessed_ops"],
                    continue_first_ops=left["first_page_ops"],
                    seal_next_first_ops=right["first_page_ops"],
                    continue_gained=len(difference["gained"]),
                    continue_lost=len(difference["lost"]),
                    continue_paid=left["paid"],
                    seal_paid=right["paid"],
                    continue_seconds=left["wall"],
                    seal_seconds=right["wall"],
                )
            )
    for version, observations in (("initial", pairs), ("refreshed", refreshed)):
        sources = Counter()
        for row in observations:
            arm = row["policy_realization"]["continue"]
            if row["teacher_potential"]["witnesses"] and arm["first_page_ops"] == 0:
                reason = (
                    "signed_no_increment"
                    if arm["requests"]
                    else "attempted_no_complete_token"
                    if arm["first_page_device"].get("neural_slot_attempts")
                    else "no_slot_attempt"
                )
                sources[reason] += 1
        summary[version + "_productive_window_zero_realized"] = sources
    table(dest / "allocations.csv", allocations)
    examples = [
        r
        for r in pairs
        if r["teacher_potential"]["witnesses"]
        and r["policy_realization"]["continue"]["first_page_ops"] == 0
    ]
    write(dest / "paired-example.json", examples[0] if examples else None)
    for group in ("egg-dual",):
        summary[group] = {
            p.stem: count_evidence(
                [(e["teacher_ops"], e["realized_ops"]) for e in read(p)]
            )
            for p in sorted((a.out / group).glob("*.json"))
        }
    for k in ("quality", "inventory", "pooled", "fit-dual"):
        summary[k] = read(a.out / (k + ".json"))
    write(dest / "experience.json", summary)
    runs = []
    groups = defaultdict(dict)
    for f in sorted((a.out / "native").glob("**/run.json")):
        s = read(f)
        seed = int(f.relative_to(a.out / "native").parts[0])
        if s["termination"] != "schedule_end":
            raise ValueError("truncated execution: " + str(f))
        case, arm = s["case"], s["method"]
        identity = (s["facts"], s["state_sha"], s["paid"], s["signed_ops"])
        seen = groups[case, arm].setdefault(seed, identity)
        if seen != identity:
            raise ValueError("timing replicate changed behavior")
        runs.append(
            dict(
                case=case,
                arm=arm,
                seed=seed,
                block=s["block"],
                facts=s["covered"],
                reference=s["reference"],
                paid=s["paid"],
                ops=s["signed_ops"],
                ept=s["ept"],
                cold_eps=s["cold_eps"],
                seconds=s["cold_wall"],
                state_sha=s["state_sha"],
                slot_attempts=s["device"].get("neural_slot_attempts", 0),
                complete_shortfall=s["device"].get("complete_shortfall", 0),
            )
        )
    if len(runs) != 48:
        raise ValueError(f"expected 48 timing runs, got {len(runs)}")
    table(dest / "runs.csv", runs)
    write(
        dest / "facts.json",
        {
            f"{c}/{arm}/{seed}": ident[0]
            for (c, arm), data in groups.items()
            for seed, ident in data.items()
        },
    )
    metrics = []
    for (c, arm), seeds in sorted(groups.items()):
        rows = [e for e in runs if (e["case"], e["arm"]) == (c, arm)]
        # Each independent seed has equal weight; timing repetitions are collapsed per seed.
        per_seed = [next(r for r in rows if r["seed"] == s) for s in seeds]
        eps = [median(r["cold_eps"] for r in rows if r["seed"] == s) for s in seeds]
        metrics.append(
            dict(
                case=c,
                arm=arm,
                coverage_pct=100
                * sum(r["facts"] / r["reference"] for r in per_seed)
                / len(seeds),
                ept=sum(r["ept"] for r in per_seed) / len(seeds),
                eps=median(eps),
                min_wall=min(r["seconds"] for r in rows),
                max_wall=max(r["seconds"] for r in rows),
            )
        )
    table(dest / "metrics.csv", metrics)
    table(
        dest / "weights.csv",
        [
            dict(
                file=str(f.relative_to(a.out)),
                sha256=hashlib.sha256(f.read_bytes()).hexdigest(),
            )
            for f in sorted((a.out / "weights").glob("*/*.pt"))
        ],
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for flag in ("out", "paired", "dest"):
        p.add_argument("--" + flag, required=True, type=Path)
    report(p.parse_args())
