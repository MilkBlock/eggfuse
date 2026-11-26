"""Reconcile slot, training and native measurements. Frozen oracle is diagnostic only."""

import argparse
import hashlib
import csv
import gzip
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
import torch

from discovery_states import read
from throughput_slots import REASONS


def table(path, rows):
    with path.open("w") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys(), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def summary(rows):
    total = lambda key: sum(r[key] for r in rows)
    secs = total("seconds")
    has_native = all("native" in r for r in rows)
    n = total("proposed")
    positive = total("positive_requests") if has_native else None
    accepted = sum(r["native"].get("accepted", 0) for r in rows) if has_native else None
    return dict(
        n=len(rows),
        censored=total("censored"),
        slots=total("slots"),
        completed=total("completed"),
        proposed=n,
        p_complete=total("completed") / total("slots"),
        hit=total("hit"),
        distinct=total("distinct"),
        mean_distinct=total("distinct") / len(rows),
        native_accept=accepted,
        native_accept_rate=accepted / n if has_native and n else None,
        ms_per_accepted=1000 * secs / accepted if accepted else None,
        positive_requests=positive,
        ops=total("ops") if has_native else None,
        sample_seconds=secs,
        ms_per_positive=1000 * secs / positive if positive else None,
    )


def paired(a):
    raw = []
    group = defaultdict(list)
    for f in sorted((a.out / "paired").glob("*/*/[0-9]*.json")):
        src, case, name = f.parts[-3:]
        for row in read(f):
            x = dict(source=src, case=case, run=int(f.stem), **row)
            group[src, case, x["run"], x["draw"], x["kind"], x["budget"]].append(x)
            raw.append(x)
    aggregates = defaultdict(list)
    for key, batch in group.items():
        arms = {r["arm"] for r in batch}
        if len(arms) != len(batch) or len(arms) != 11:
            raise ValueError("incomplete paired comparison")
        primary = (
            "initial",
            "dual-witness",
            "conservative",
            "isolate-no-inactive",
            "factored",
        )
        matched = all(not r["censored"] for r in batch if r["arm"] in primary)
        for r in batch:
            for cohort in ("all", r["source"]):
                base = (cohort, r["arm"], r["kind"], r["budget"])
                aggregates[base + ("all",)].append(r)
                if r["kind"] == "complete" and r["arm"] in primary and matched:
                    aggregates[base + ("matched_primary",)].append(r)
    count = len(set((r["source"], r["case"], r["run"]) for r in raw))
    if count != 58:
        raise ValueError(f"expected 58 paired starts, got {count}")
    table(
        a.dest / "paired.csv",
        [
            dict(source=s, arm=arm, kind=k, budget=b, population=p, **summary(rs))
            for (s, arm, k, b, p), rs in sorted(aggregates.items())
        ],
    )


def funnels(a):
    rs = []
    failures = []
    for arm in ("initial", "dual-witness"):
        d = read(a.out / "observed" / arm / "fact.json")
        c = d["counts"]
        reasons = Counter()
        for tid, depth, why, n in d["failures"]:
            reasons["first" if not depth else "later"] += n
            failures.append(
                dict(
                    arm=arm,
                    rule=tid // 2,
                    higher=tid % 2,
                    slot=depth,
                    reason=why,
                    count=n,
                )
            )
        rs.append(
            dict(
                arm=arm,
                attempted=c["slot_attempts"],
                empty_slot=0,
                no_template=0,
                selected_template=c["selected_templates"],
                parent_failure_first=reasons["first"],
                parent_failure_later=reasons["later"],
                empty_table=c.get(REASONS[0], 0),
                missing_projection=c.get(REASONS[1], 0),
                wrong_table=c.get(REASONS[2], 0),
                complete=c["complete"],
                edit_delete=0,
                repeat_edit=0,
                control=0,
                over_goal=c["over_goal"],
                returned=c["returned"],
                unaccounted=0,
                suffix=c["paid_higher_suffix"],
                paid=c["paid"],
                shortfall=c["shortfall"],
            )
        )
    table(a.dest / "funnels.csv", rs)
    table(a.dest / "failure-rules.csv", failures)


def formal(a):
    rows = []
    facts = {}
    for root in (a.out, a.donor):
        for f in sorted((root / "native").glob("**/run.json")):
            r = read(f)
            arm = r["method"]
            if root == a.donor and arm != "dual-witness":
                continue
            seed = int(f.relative_to(root / "native").parts[0])
            case = r["case"]
            if r["termination"] != "schedule_end":
                raise ValueError("incomplete run")
            key = f"{case}/{arm}/{seed}"
            values = (r["state_sha"], r["facts"], r["paid"], r["signed_ops"])
            if facts.setdefault(key, values) != values:
                raise ValueError("timing replica diverged")
            rows.append(
                dict(
                    case=case,
                    arm=arm,
                    seed=seed,
                    block=r["block"],
                    facts=r["covered"],
                    reference=r["reference"],
                    ops=r["signed_ops"],
                    paid=r["paid"],
                    ept=r["ept"],
                    eps=r["cold_eps"],
                    seconds=r["cold_wall"],
                    slot_attempts=r["device"].get("neural_slot_attempts", 0),
                    shortfall=r["device"].get("complete_shortfall", 0),
                )
            )
    if len(rows) != 60:
        raise ValueError("missing formal runs")
    table(a.dest / "runs.csv", rows)
    (a.dest / "facts.json").write_text(json.dumps(facts, separators=(",", ":")) + "\n")
    out = []
    for key in sorted({(x["case"], x["arm"]) for x in rows}):
        pop = [x for x in rows if (x["case"], x["arm"]) == key]
        first = [r for r in pop if r["block"] == 0]
        eps = [median(r["eps"] for r in pop if r["seed"] == s) for s in (5003, 9633)]
        out.append(
            dict(
                case=key[0],
                arm=key[1],
                coverage_pct=100
                * sum(r["facts"] / r["reference"] for r in first)
                / len(first),
                ept=sum(r["ept"] for r in first) / len(first),
                eps=median(eps),
                slots_per_paid=sum(r["slot_attempts"] for r in first)
                / sum(r["paid"] for r in first)
                if key[1] != "factored"
                else None,
            )
        )
    table(a.dest / "formal.csv", out)


def checks(a):
    source = next((a.out / "observer-regression/buffer").glob("*.gz"))
    with gzip.open(source) as f:
        sh = json.load(f)
    with gzip.open(next((a.donor / "buffer").glob("0000-2-*.gz"))) as f:
        original = json.load(f)
    for e, old in zip(sh["events"], original["events"], strict=True):
        if any(
            e[k] != old[k]
            for k in (
                "generated",
                "response",
                "signed_gain",
                "omitted",
                "semantic_state",
            )
        ):
            raise ValueError("collector observer changed trajectory")
        if (
            len(e["slot_attempts"]) != 160
            or e["unsubmitted_credit_mask"]
            or sum(not s[1] for s in e["slot_attempts"]) != len(e["generated"])
        ):
            raise ValueError("incomplete slot experiences")
    diff = {}
    for seed in ("9633", "5003"):
        old = torch.load(
            a.donor / "weights" / seed / "dual-witness.pt", weights_only=True
        )
        new = torch.load(
            a.out / "weights" / seed / "isolate-witness.pt", weights_only=True
        )
        diff[seed] = max(float((v - new[k]).abs().max()) for k, v in old.items())
        if diff[seed] > 1e-5:
            raise ValueError("historical training replay diverged")
    return dict(
        max_parameter_replay_error=diff, collector_identical_windows=len(sh["events"])
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for k in ("out", "donor", "dest"):
        p.add_argument("--" + k, type=Path, required=True)
    a = p.parse_args()
    a.dest.mkdir(parents=True, exist_ok=True)
    funnels(a)
    paired(a)
    formal(a)
    transfer = defaultdict(Counter)
    for path in sorted((a.out / "transfer").glob("*.json")):
        for r in read(path):
            transfer[r["arm"]].update(
                {k: v for k, v in r.items() if isinstance(v, int) and k != "run"}
            )
    table(
        a.dest / "transfer.csv", [dict(arm=k, **v) for k, v in sorted(transfer.items())]
    )

    table(
        a.dest / "weights.csv",
        [
            dict(
                file=str(f.relative_to(a.out)),
                sha256=hashlib.sha256(f.read_bytes()).hexdigest(),
            )
            for f in sorted((a.out / "weights").glob("*/*.pt"))
        ],
    )
    (a.dest / "training.json").write_text(
        json.dumps(dict(read(a.out / "exposure.json"), checks=checks(a)), indent=2)
        + "\n"
    )
