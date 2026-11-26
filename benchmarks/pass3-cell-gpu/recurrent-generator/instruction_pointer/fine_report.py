"""Publish compact measurements; each row resolves to a raw rollout or replay fork."""

import argparse
import csv
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median


def read(path):
    return json.loads(path.read_bytes())


def save(path, v):
    path.write_text(json.dumps(v, indent=2) + "\n")


def table(path, rows):
    if not rows:
        raise ValueError(f"empty table {path}")
    with path.open("w") as out:
        w = csv.DictWriter(
            out, list(dict.fromkeys(k for r in rows for k in r)), lineterminator="\n"
        )
        w.writeheader()
        w.writerows(rows)


def grouped(rows, keys):
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(row[k] for k in keys)].append(row)
    return groups


def report(a):
    root = a.root
    dest = a.dest
    dest.mkdir(parents=True, exist_ok=True)
    raw = []
    factsets = {}
    for path in sorted((root / "native").glob("*/*/native-address/*/*/run.json")):
        v = read(path)
        case, arm = v["case"], v["method"]
        sign = hashlib.sha256(
            json.dumps(v["facts"], separators=(",", ":")).encode()
        ).hexdigest()
        factsets[case, sign] = v["facts"]
        row = {
            k: v[k]
            for k in (
                "case",
                "block",
                "covered",
                "reference",
                "paid",
                "signed_ops",
                "ept",
                "cold_wall",
                "cold_eps",
                "state_sha",
                "termination",
            )
        }
        row.update(
            seed=path.relative_to(root).parts[1],
            arm=arm,
            fact_set=sign,
            slots=v["device"].get("neural_slot_attempts", 0),
            shortfall=v["device"].get("complete_shortfall", 0),
            sync=v["synchronizations"],
            **v["verdicts"],
        )
        raw.append(row)
    table(dest / "native-runs.csv", raw)
    summary = []
    for (case, arm), rows in sorted(grouped(raw, ["case", "arm"]).items()):
        outcomes = [r for r in rows if r["block"] == 0]
        if not outcomes:
            continue
        s = Counter()
        for r in outcomes:
            for k in (
                "covered",
                "reference",
                "paid",
                "signed_ops",
                "accepted",
                "untriggered_rule",
                "binding",
                "guard",
                "duplicate",
                "slots",
                "shortfall",
            ):
                s[k] += r.get(k, 0)
        summary.append(
            dict(
                case=case,
                arm=arm,
                seeds=len(outcomes),
                runs=len(rows),
                coverage=s["covered"] / s["reference"],
                EPT=s["signed_ops"] / s["paid"],
                EPS=median(r["cold_eps"] for r in rows),
                wall_min=min(r["cold_wall"] for r in rows),
                wall_max=max(r["cold_wall"] for r in rows),
                **s,
            )
        )
    table(dest / "native.csv", summary)
    diffs = []
    for (case, seed), rows in grouped(
        [r for r in raw if r["block"] == 0], ["case", "seed"]
    ).items():
        by = {r["arm"]: r for r in rows}
        for arm in sorted(by):
            for base in ("factored", "full-A", "initial"):
                if base not in by:
                    continue
                lhs = set(factsets[case, by[arm]["fact_set"]])
                rhs = set(factsets[case, by[base]["fact_set"]])
                diffs.append(
                    {
                        "case": case,
                        "seed": seed,
                        "arm": arm,
                        "baseline": base,
                        "intersection": len(lhs & rhs),
                        "gained": len(lhs - rhs),
                        "lost": len(rhs - lhs),
                        "same_terminal": by[arm]["state_sha"] == by[base]["state_sha"],
                    }
                )
    table(dest / "fact-differences.csv", diffs)
    with (dest / "fact-sets.jsonl").open("w") as out:
        for (case, h), fs in sorted(factsets.items()):
            out.write(json.dumps([case, h, fs]) + "\n")
    held = []
    for path in sorted(root.glob("held-*.jsonl")):
        held.extend(json.loads(line) for line in path.read_text().splitlines())
    result = []
    for (arm,), rows in sorted(grouped(held, ["arm"]).items()):
        totals = Counter()
        for r in rows:
            for k, v in r.items():
                if isinstance(v, (int, float)) and k not in ("EPT", "EPS", "seed"):
                    totals[k] += v

        def ratio(a, b, totals=totals):
            return totals[a] / totals[b] if totals[b] else None

        result.append(
            dict(
                arm=arm,
                runs=len(rows),
                Coverage=ratio("covered", "reference"),
                EPT=ratio("ops", "paid"),
                EPS=ratio("ops", "seconds"),
                paired_accuracy=ratio("paired_right", "paired_total"),
                replacement_accuracy=ratio("substitution_right", "substitution_total"),
                mean_valid_parents=ratio(
                    "conditional_parent_prob_sum", "known_valid_tuple_count"
                ),
                mean_p_productive=ratio("prob_unfinished", "paired_total"),
                mean_p_done=ratio("prob_done", "paired_total"),
                mean_p_causal_parent=ratio("upstream_prob_sum", "observed_path_count"),
                **totals,
            )
        )
    table(dest / "held.csv", result)
    demos = []
    manifest = []
    counts = Counter()
    small = Counter()
    for path in sorted((root / "buffer").glob("*.gz")):
        with gzip.open(path) as f:
            s = json.load(f)
        with gzip.open(root / "credit" / path.name) as f:
            side = json.load(f)
        ng = sum(len(e["generated"]) for e in s["events"])
        no = sum(len(e["omitted"]) for e in s["events"])
        ids = {r[0] for e in s["events"] for r in e["response"]}
        deps = {p for _, p, _, c, _ in side["edges"] if p in ids}
        counts["neural_signed_parents_on_verified_suffixes"] += len(deps)
        counts["both_endpoints_neural"] += sum(
            p in ids and c in ids for _, p, _, c, _ in side["edges"]
        )
        counts["signed_tokens_new_ops"] += sum(
            g > 0 for e in s["events"] for g in e["signed_gain"]
        )
        counts["native_audit_worker_seconds"] += s["cost"]["audit_seconds"]
        if s["idx"] < 16:
            small.update(tokens=ng, omissions=no, frames=len(s["events"]))
        manifest.append(
            {
                "program": s["idx"],
                "branch": s["branch"],
                "seed": s["rollout_seed"],
                "checkpoint": s["checkpoint"],
                "recipe": s["program"],
                "structure": s["signature"],
                "source": path.name,
                "source_sha": side["source_sha256"],
                "derived_sha": hashlib.sha256(
                    (root / "credit" / path.name).read_bytes()
                ).hexdigest(),
                "tokens": ng,
                "omissions": no,
                "rows": len(s["events"]),
                "substitutions": len(side["edits"]),
                "dependencies": len(side["edges"]),
            }
        )
        if side["edits"] and side["edges"] and len(demos) < 4:
            demos.append(
                {
                    "source": path.name,
                    "edit": side["edits"][0],
                    "edge": side["edges"][0],
                }
            )
    table(dest / "shards.csv", manifest)
    save(dest / "replay-examples.json", demos)
    stats = read(root / "quality.json")
    save(dest / "quality.json", {**stats, **counts, "nested_first_16": small})
    order = []
    for source in ("held-fixed", "held-complete-fixed"):
        prior = root.parent / (source + ".jsonl")
        if not prior.exists():
            continue
        for (arm,), entries in grouped(
            [json.loads(line) for line in prior.read_text().splitlines()], ["arm"]
        ).items():
            sums = {
                k: sum(item.get(k, 0) for item in entries)
                for k in ("paid", "covered", "reference", "ops", "right", "pairs")
            }
            order.append(
                dict(
                    panel=source,
                    arm=arm,
                    coverage=sums["covered"] / sums["reference"],
                    EPT=sums["ops"] / sums["paid"],
                    **sums,
                )
            )
    if order:
        table(dest / "matched-distribution.csv", order)
    audits = []
    for name, loc in (
        ("initial_dynamic", root.parent),
        ("alternate_trajectory", root.parent / "diverse"),
        ("fine", root),
    ):
        if (loc / "quality.json").exists():
            audits.append(dict(source=name, **read(loc / "quality.json")))
    table(dest / "quality-by-cohort.csv", audits)
    if (root / "egg-audit.json").exists():
        save(dest / "egg-audit.json", read(root / "egg-audit.json"))
    if (root / "clock.csv").exists():
        (dest / "clock.csv").write_bytes((root / "clock.csv").read_bytes())
    hist = Path(__file__).parent / "run-recall/credit-scaling/historical-stream.csv"
    (dest / "historical-stream.csv").write_bytes(hist.read_bytes())
    timing = []
    for path in sorted(
        (root / "timing/native").glob("*/*/native-address/*/*/run.json")
    ):
        v = read(path)
        timing.append(
            {
                k: v[k]
                for k in (
                    "case",
                    "method",
                    "block",
                    "covered",
                    "reference",
                    "paid",
                    "signed_ops",
                    "ept",
                    "cold_wall",
                    "cold_eps",
                    "state_sha",
                )
            }
        )
    if timing:
        table(dest / "isolated-timing.csv", timing)
    sizes = {
        name: sum(p.stat().st_size for p in (root / name).rglob("*") if p.is_file())
        for name in ("buffer", "credit", "weights")
    }
    save(
        dest / "production.json",
        {
            "collection": read(next(root.glob("collection-0-80-*.json"))),
            "new_cohort_logical_bytes": sizes,
            "audit_worker_seconds": counts["native_audit_worker_seconds"],
            "credit_verification_seconds": stats["worker_wall_seconds"],
        },
    )
    digest = []
    for path in sorted((root / "weights").glob("*/*.pt")):
        digest.append(
            {
                "path": str(path.relative_to(root)),
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    table(dest / "weights.csv", digest)
    for fname in (
        "port-controls",
        "native-controls",
        "higher-control",
        "fine-inventory",
        "pooled-inventory",
        "fit-full",
        "fit-full-small",
        "fit-small",
    ):
        save(dest / (fname + ".json"), read(root / (fname + ".json")))
    save(
        dest / "fit-slot.json",
        read(
            root
            / ("fit-fine.json" if (root / "fit-fine.json").exists() else "fit.json")
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for key in ("root", "dest"):
        p.add_argument(key, type=Path)
    report(p.parse_args())
